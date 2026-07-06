from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from app.services.ai_writer import AISettings, generate_email_draft
from app.services.importer import LeadDataset, extract_email_address
from app.services.smtp_service import (
    SMTPConfig,
    SMTPConfigError,
    is_retryable_smtp_error,
    send_email,
)
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
) -> int:
    settings = settings or BatchSendSettings()
    accounts = build_accounts_from_storage(storage)
    if not accounts:
        raise BatchSendError("账号池为空，请先保存至少一个 SMTP 账号。")

    email_header = dataset.field_mapping.get("email")
    if not email_header:
        raise BatchSendError("当前名单没有映射邮箱字段，无法批量发送。")

    task_id = storage.create_send_task(task_label, dataset.source_path, dataset.total_rows)
    started_at = datetime.now().isoformat(timespec="seconds")
    storage.update_send_task(task_id, "running", 0, 0, started_at=started_at)
    normalized_recipient_emails = [
        extract_email_address(row.get(email_header, ""))
        for row in dataset.rows
    ]
    prior_sent_counts = storage.list_prior_sent_counts(normalized_recipient_emails)

    success_count = 0
    failure_count = 0
    skipped_count = 0
    review_count = 0

    for index, row in enumerate(dataset.rows):
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
        duplicate_count = 0
        subject = ""
        body = ""

        if not recipient_email:
            status = "failed"
            error_message = f"收件邮箱为空或格式无效：{raw_recipient_value or '空值'}"
            failure_count += 1
        else:
            duplicate_count = prior_sent_counts.get(recipient_email.lower(), 0)
            if duplicate_count > 0:
                if duplicate_policy == "review":
                    status = "review_required"
                    error_message = f"该邮箱历史已发送 {duplicate_count} 次，等待人工审核"
                    review_count += 1
                elif duplicate_policy == "skip":
                    status = "skipped_duplicate"
                    error_message = f"该邮箱历史已发送 {duplicate_count} 次，按策略自动忽略"
                    skipped_count += 1
            if status == "sent":
                draft = generate_email_draft(template, row, dataset, index, ai_settings)
                subject = draft.subject
                body = draft.body
            else:
                subject, body = _build_template_draft(template, row, dataset)

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
                    success_count += 1
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
                    failure_count += 1
                    break
            else:
                status = "failed"
                error_message = final_error or "SMTP 发送失败。"
                failure_count += 1
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

        if settings.per_email_delay_seconds > 0 and index < dataset.total_rows - 1:
            if stop_event.wait(settings.per_email_delay_seconds):
                storage.update_send_task(
                    task_id,
                    "stopped",
                    success_count,
                    failure_count,
                    skipped_count=skipped_count,
                    review_count=review_count,
                )
                return task_id

    finished_at = datetime.now().isoformat(timespec="seconds")
    if failure_count:
        final_status = "completed_with_errors"
    elif review_count:
        final_status = "completed_with_review"
    elif skipped_count:
        final_status = "completed_with_skips"
    else:
        final_status = "completed"
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
