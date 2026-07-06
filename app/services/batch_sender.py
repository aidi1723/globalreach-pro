from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
from typing import Callable

from app.services.ai_writer import AISettings, generate_email_draft
from app.services.importer import LeadDataset, extract_email_address
from app.services.smtp_service import (
    SMTPConfig,
    SMTPConfigError,
    is_retryable_smtp_error,
    send_email,
)
from app.services.send_policy import SendDecision, SendPolicyService
from app.services.send_quota import SendQuotaService
from app.services.suppression import SuppressionService
from app.services.template import render_template, split_subject_and_body
from app.storage.db import AppStorage


class BatchSendError(Exception):
    pass


@dataclass
class SMTPAccount:
    label: str
    config: SMTPConfig


@dataclass
class BatchProgress:
    row_index: int
    total_count: int
    recipient_email: str
    account_label: str
    status: str
    error_message: str = ""
    duplicate_count: int = 0
    attempt_number: int = 0
    max_attempts: int = 0


@dataclass
class BatchSendSettings:
    per_email_delay_seconds: float = 0.0
    max_retries: int = 0
    retry_backoff_seconds: float = 1.0


@dataclass
class GovernanceSettings:
    daily_limit_per_account: int = 0
    hourly_limit_per_account: int = 0
    quota_now: str | None = None


def build_accounts_from_storage(storage: AppStorage) -> list[SMTPAccount]:
    accounts = []
    for item in storage.list_smtp_accounts():
        config = SMTPConfig.from_state(
            {
                "smtp_provider": item["provider"],
                "smtp_host": item["host"],
                "smtp_port": item["port"],
                "smtp_username": item["username"],
                "smtp_password": item["password"],
                "smtp_sender_email": item["sender_email"],
                "smtp_sender_name": item["sender_name"],
                "smtp_security": item["security"],
                "smtp_dkim_selector": item["dkim_selector"],
            }
        )
        accounts.append(SMTPAccount(label=item["label"], config=config))
    return accounts


def _build_template_draft(template: str, row: dict[str, str], dataset: LeadDataset) -> tuple[str, str]:
    rendered, _issues = render_template(template, row, dataset)
    return split_subject_and_body(rendered)


def _counts_from_status_summary(summary: dict[str, int]) -> tuple[int, int, int, int]:
    success_count = summary.get("sent", 0)
    failure_count = summary.get("failed", 0)
    skipped_count = (
        summary.get("skipped_duplicate", 0)
        + summary.get("suppressed", 0)
        + summary.get("rate_limited", 0)
    )
    review_count = summary.get("review_required", 0)
    return success_count, failure_count, skipped_count, review_count


def _non_send_error_message(
    decision: SendDecision,
    raw_recipient_value: str,
    duplicate_count: int,
) -> str:
    if decision.code == "invalid_email":
        return f"收件邮箱为空或格式无效：{raw_recipient_value or '空值'}"
    if decision.status == "review_required":
        return f"该邮箱历史已发送 {duplicate_count} 次，等待人工审核"
    if decision.status == "skipped_duplicate":
        return f"该邮箱历史已发送 {duplicate_count} 次，按策略自动忽略"
    return decision.message


def _increment_counts_for_status(
    status: str,
    success_count: int,
    failure_count: int,
    skipped_count: int,
    review_count: int,
) -> tuple[int, int, int, int]:
    if status == "sent":
        success_count += 1
    elif status == "failed":
        failure_count += 1
    elif status == "review_required":
        review_count += 1
    elif status in {"skipped_duplicate", "suppressed", "rate_limited"}:
        skipped_count += 1
    return success_count, failure_count, skipped_count, review_count


def _final_task_status(failure_count: int, skipped_count: int, review_count: int) -> str:
    if failure_count:
        return "completed_with_errors"
    if review_count:
        return "completed_with_review"
    if skipped_count:
        return "completed_with_skips"
    return "completed"


def _normalized_source_path(source_path: str) -> Path:
    return Path(source_path).expanduser().resolve(strict=False)


def _dataset_fingerprint(dataset: LeadDataset) -> str:
    payload = {
        "headers": dataset.headers,
        "rows": dataset.rows,
        "field_mapping": dataset.field_mapping,
    }
    raw_value = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


def _wait_for_delay_signal(stop_event, pause_event, delay_seconds: float) -> str:
    deadline = time.monotonic() + max(0.0, delay_seconds)
    poll_interval = 0.1
    while True:
        if stop_event.is_set():
            return "stop"
        if pause_event is not None and pause_event.is_set():
            return "stop" if stop_event.is_set() else "pause"

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return ""
        if stop_event.wait(min(poll_interval, remaining)):
            return "stop"


def run_batch_send(
    storage: AppStorage,
    dataset: LeadDataset,
    template: str,
    ai_settings: AISettings,
    task_label: str,
    duplicate_policy: str,
    stop_event,
    attachment_paths: list[str] | None = None,
    settings: BatchSendSettings | None = None,
    progress_callback: Callable[[BatchProgress], None] | None = None,
    governance: GovernanceSettings | None = None,
    pause_event=None,
    resume_task_id: int | None = None,
) -> int:
    settings = settings or BatchSendSettings()
    governance = governance or GovernanceSettings()
    quota_service = SendQuotaService(storage)
    policy_service = SendPolicyService(
        storage,
        SuppressionService(storage),
        quota_service,
    )
    accounts = build_accounts_from_storage(storage)
    if not accounts:
        raise BatchSendError("账号池为空，请先保存至少一个 SMTP 账号。")

    email_header = dataset.field_mapping.get("email")
    if not email_header:
        raise BatchSendError("当前名单没有映射邮箱字段，无法批量发送。")

    if resume_task_id is not None:
        task = storage.get_send_task(resume_task_id)
        if task is None:
            raise BatchSendError("要恢复的任务不存在。")
        if task["status"] != "paused":
            raise BatchSendError("只有已暂停的任务可以恢复。")
        if _normalized_source_path(dataset.source_path) != _normalized_source_path(task["source_file"]):
            raise BatchSendError("恢复任务的名单文件不匹配。")
        if dataset.total_rows != int(task["total_count"]):
            raise BatchSendError("恢复任务的名单行数不匹配。")
        stored_fingerprint = task.get("dataset_fingerprint", "")
        if stored_fingerprint and stored_fingerprint != _dataset_fingerprint(dataset):
            raise BatchSendError("恢复任务的名单内容不匹配。")
        task_id = resume_task_id
        recorded_row_indexes = storage.list_recorded_row_indexes(task_id)
        success_count, failure_count, skipped_count, review_count = _counts_from_status_summary(
            storage.summarize_task_results(task_id)
        )
    else:
        task = None
        task_id = storage.create_send_task(
            task_label,
            dataset.source_path,
            dataset.total_rows,
            dataset_fingerprint=_dataset_fingerprint(dataset),
        )
        recorded_row_indexes = set()
        success_count = 0
        failure_count = 0
        skipped_count = 0
        review_count = 0

    started_at = datetime.now().isoformat(timespec="seconds")
    storage.update_send_task(
        task_id,
        "running",
        success_count,
        failure_count,
        skipped_count=skipped_count,
        review_count=review_count,
        started_at="" if task and task.get("started_at") else started_at,
    )
    normalized_recipient_emails = [
        extract_email_address(row.get(email_header, ""))
        for row in dataset.rows
    ]
    prior_sent_counts = storage.list_prior_sent_counts(normalized_recipient_emails)

    for index, row in enumerate(dataset.rows):
        if index in recorded_row_indexes:
            continue

        if stop_event.is_set():
            storage.update_send_task(
                task_id,
                "stopped",
                success_count,
                failure_count,
                skipped_count=skipped_count,
                review_count=review_count,
            )
            return task_id

        account = accounts[index % len(accounts)]
        raw_recipient_value = str(row.get(email_header, "")).strip()
        recipient_email = normalized_recipient_emails[index]
        status = "sent"
        error_message = ""
        duplicate_count = prior_sent_counts.get(recipient_email.lower(), 0)
        subject = ""
        body = ""

        decision = policy_service.evaluate(
            recipient_email=recipient_email,
            duplicate_count=duplicate_count,
            duplicate_policy=duplicate_policy,
            account_label=account.label,
            daily_limit=governance.daily_limit_per_account,
            hourly_limit=governance.hourly_limit_per_account,
            now=governance.quota_now,
        )
        if decision.should_send:
            draft = generate_email_draft(template, row, dataset, index, ai_settings)
            subject = draft.subject
            body = draft.body
        else:
            status = decision.status
            error_message = _non_send_error_message(decision, raw_recipient_value, duplicate_count)
            subject, body = _build_template_draft(template, row, dataset)
            success_count, failure_count, skipped_count, review_count = _increment_counts_for_status(
                status,
                success_count,
                failure_count,
                skipped_count,
                review_count,
            )

        if status == "sent":
            max_attempts = max(1, settings.max_retries + 1)
            final_error = ""
            for attempt_number in range(1, max_attempts + 1):
                if progress_callback is not None:
                    progress_callback(
                        BatchProgress(
                            row_index=index,
                            total_count=dataset.total_rows,
                            recipient_email=recipient_email,
                            account_label=account.label,
                            status="attempting",
                            duplicate_count=duplicate_count,
                            attempt_number=attempt_number,
                            max_attempts=max_attempts,
                        )
                    )
                try:
                    send_email(
                        account.config,
                        recipient_email=recipient_email,
                        subject=subject,
                        body=body,
                        attachment_paths=attachment_paths,
                    )
                    quota_service.record_sent(
                        account.label,
                        recipient_email,
                        task_id,
                        sent_at=governance.quota_now,
                    )
                    success_count, failure_count, skipped_count, review_count = (
                        _increment_counts_for_status(
                            "sent",
                            success_count,
                            failure_count,
                            skipped_count,
                            review_count,
                        )
                    )
                    prior_sent_counts[recipient_email.lower()] = duplicate_count + 1
                    status = "sent"
                    error_message = ""
                    break
                except SMTPConfigError as exc:
                    final_error = str(exc)
                    retryable = is_retryable_smtp_error(exc)
                    if retryable and attempt_number < max_attempts and not stop_event.is_set():
                        if progress_callback is not None:
                            progress_callback(
                                BatchProgress(
                                    row_index=index,
                                    total_count=dataset.total_rows,
                                    recipient_email=recipient_email,
                                    account_label=account.label,
                                    status="retrying",
                                    error_message=final_error,
                                    duplicate_count=duplicate_count,
                                    attempt_number=attempt_number,
                                    max_attempts=max_attempts,
                                )
                            )
                        if stop_event.wait(settings.retry_backoff_seconds):
                            storage.update_send_task(
                                task_id,
                                "stopped",
                                success_count,
                                failure_count,
                                skipped_count=skipped_count,
                                review_count=review_count,
                            )
                            return task_id
                        continue

                    status = "failed"
                    error_message = final_error
                    success_count, failure_count, skipped_count, review_count = (
                        _increment_counts_for_status(
                            "failed",
                            success_count,
                            failure_count,
                            skipped_count,
                            review_count,
                        )
                    )
                    break
            else:
                status = "failed"
                error_message = final_error or "SMTP 发送失败。"
                success_count, failure_count, skipped_count, review_count = _increment_counts_for_status(
                    "failed",
                    success_count,
                    failure_count,
                    skipped_count,
                    review_count,
                )
        storage.add_send_result(
            task_id=task_id,
            row_index=index,
            recipient_email=recipient_email,
            account_label=account.label,
            subject=subject,
            body=body,
            status=status,
            error_message=error_message,
        )
        storage.update_send_task(
            task_id,
            "running",
            success_count,
            failure_count,
            skipped_count=skipped_count,
            review_count=review_count,
        )

        if progress_callback is not None:
            progress_callback(
                BatchProgress(
                    row_index=index,
                    total_count=dataset.total_rows,
                    recipient_email=recipient_email,
                    account_label=account.label,
                    status=status,
                    error_message=error_message,
                    duplicate_count=duplicate_count,
                )
            )

        if stop_event.is_set():
            storage.update_send_task(
                task_id,
                "stopped",
                success_count,
                failure_count,
                skipped_count=skipped_count,
                review_count=review_count,
            )
            return task_id

        if pause_event is not None and pause_event.is_set():
            storage.update_send_task(
                task_id,
                "paused",
                success_count,
                failure_count,
                skipped_count=skipped_count,
                review_count=review_count,
            )
            return task_id

        if settings.per_email_delay_seconds > 0 and index < dataset.total_rows - 1:
            delay_signal = _wait_for_delay_signal(
                stop_event,
                pause_event,
                settings.per_email_delay_seconds,
            )
            if delay_signal == "stop":
                storage.update_send_task(
                    task_id,
                    "stopped",
                    success_count,
                    failure_count,
                    skipped_count=skipped_count,
                    review_count=review_count,
                )
                return task_id
            if delay_signal == "pause":
                storage.update_send_task(
                    task_id,
                    "paused",
                    success_count,
                    failure_count,
                    skipped_count=skipped_count,
                    review_count=review_count,
                )
                return task_id

    success_count, failure_count, skipped_count, review_count = _counts_from_status_summary(
        storage.summarize_task_results(task_id)
    )
    finished_at = datetime.now().isoformat(timespec="seconds")
    final_status = _final_task_status(failure_count, skipped_count, review_count)
    storage.update_send_task(
        task_id,
        final_status,
        success_count,
        failure_count,
        skipped_count=skipped_count,
        review_count=review_count,
        finished_at=finished_at,
    )
    return task_id
