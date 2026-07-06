from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.storage.db import AppStorage


@dataclass
class QuotaDecision:
    allowed: bool
    code: str = ""
    message: str = ""


def _quota_datetime(value: str | None = None) -> datetime:
    parsed = datetime.fromisoformat(value) if value else datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_quota_datetime(value: datetime) -> str:
    return value.replace(tzinfo=None).isoformat(timespec="seconds")


def _quota_timestamp(value: str | None = None) -> str:
    return _format_quota_datetime(_quota_datetime(value))


class SendQuotaService:
    def __init__(self, storage: AppStorage):
        self.storage = storage

    def check(
        self,
        account_label: str,
        daily_limit: int = 0,
        hourly_limit: int = 0,
        now: str | None = None,
    ) -> QuotaDecision:
        current = _quota_datetime(now)
        current_at = _format_quota_datetime(current)
        if daily_limit > 0:
            day_start = _format_quota_datetime(current - timedelta(days=1))
            daily_count = self.storage.count_account_usage_between(
                account_label,
                day_start,
                current_at,
            )
            if daily_count >= daily_limit:
                return QuotaDecision(
                    False,
                    "daily_limit_reached",
                    f"{account_label} 已达到每日发送上限 {daily_limit}。",
                )
        if hourly_limit > 0:
            hour_start = _format_quota_datetime(current - timedelta(hours=1))
            hourly_count = self.storage.count_account_usage_between(
                account_label,
                hour_start,
                current_at,
            )
            if hourly_count >= hourly_limit:
                return QuotaDecision(
                    False,
                    "hourly_limit_reached",
                    f"{account_label} 已达到每小时发送上限 {hourly_limit}。",
                )
        return QuotaDecision(True)

    def record_sent(
        self,
        account_label: str,
        recipient_email: str,
        task_id: int,
        sent_at: str | None = None,
    ) -> None:
        timestamp = _quota_timestamp(sent_at)
        self.storage.add_account_send_usage(account_label, recipient_email, task_id, timestamp)
