from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.storage.db import AppStorage


@dataclass
class QuotaDecision:
    allowed: bool
    code: str = ""
    message: str = ""


def _parse_now(now: str | None = None) -> datetime:
    if now:
        return datetime.fromisoformat(now)
    return datetime.now()


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
        current = _parse_now(now)
        if daily_limit > 0:
            day_start = current.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(
                timespec="seconds"
            )
            daily_count = self.storage.count_account_usage_since(account_label, day_start)
            if daily_count >= daily_limit:
                return QuotaDecision(
                    False,
                    "daily_limit_reached",
                    f"{account_label} 已达到每日发送上限 {daily_limit}。",
                )
        if hourly_limit > 0:
            hour_start = (current - timedelta(hours=1)).isoformat(timespec="seconds")
            hourly_count = self.storage.count_account_usage_since(account_label, hour_start)
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
        timestamp = sent_at or datetime.now().isoformat(timespec="seconds")
        self.storage.add_account_send_usage(account_label, recipient_email, task_id, timestamp)
