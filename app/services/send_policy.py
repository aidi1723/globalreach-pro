from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.send_quota import SendQuotaService
from app.services.suppression import SuppressionService
from app.storage.db import AppStorage


EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+$")
ALLOWED_DUPLICATE_POLICIES = {"review", "skip", "send"}


@dataclass
class SendDecision:
    status: str
    should_send: bool
    code: str = ""
    message: str = ""


def _normalize_policy_recipient_email(value: object) -> str:
    if not isinstance(value, str):
        return ""

    email = value.strip()
    if not email or not EMAIL_PATTERN.fullmatch(email):
        return ""

    local, domain = email.rsplit("@", 1)
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return ""

    labels = domain.split(".")
    if len(labels) < 2:
        return ""
    for label in labels:
        if not label or label.startswith("-") or label.endswith("-"):
            return ""

    return email.lower()


def _normalize_duplicate_count(value: object) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return count if count > 0 else 0


def _normalize_duplicate_policy(value: object) -> str:
    if not isinstance(value, str):
        return ""
    policy = value.strip().lower()
    return policy if policy in ALLOWED_DUPLICATE_POLICIES else ""


class SendPolicyService:
    def __init__(
        self,
        storage: AppStorage,
        suppression: SuppressionService,
        quota: SendQuotaService,
    ):
        self.storage = storage
        self.suppression = suppression
        self.quota = quota

    def evaluate(
        self,
        recipient_email: object,
        duplicate_count: object,
        duplicate_policy: object,
        account_label: str,
        daily_limit: int,
        hourly_limit: int,
        now: str | None = None,
    ) -> SendDecision:
        normalized_email = _normalize_policy_recipient_email(recipient_email)
        if not normalized_email:
            return SendDecision(
                status="failed",
                should_send=False,
                code="invalid_email",
                message="Invalid recipient email.",
            )

        if self.suppression.is_suppressed(normalized_email):
            return SendDecision(
                status="suppressed",
                should_send=False,
                code="suppression_match",
                message="Recipient is on the suppression list.",
            )

        prior_send_count = _normalize_duplicate_count(duplicate_count)
        if prior_send_count > 0:
            policy = _normalize_duplicate_policy(duplicate_policy)
            if policy == "skip":
                return SendDecision(
                    status="skipped_duplicate",
                    should_send=False,
                    code="duplicate_skipped",
                    message="Recipient was already sent before.",
                )
            if policy != "send":
                return SendDecision(
                    status="review_required",
                    should_send=False,
                    code="duplicate_review_required",
                    message="Recipient was already sent before and needs review.",
                )

        quota_decision = self.quota.check(
            account_label=account_label,
            daily_limit=daily_limit,
            hourly_limit=hourly_limit,
            now=now,
        )
        if not quota_decision.allowed:
            return SendDecision(
                status="rate_limited",
                should_send=False,
                code=quota_decision.code,
                message=quota_decision.message,
            )

        return SendDecision(status="send", should_send=True)
