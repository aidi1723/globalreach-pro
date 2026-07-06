from app.services.secret_store import EphemeralSecretStore
from app.services.send_quota import SendQuotaService
from app.storage.db import AppStorage


def make_storage(tmp_path):
    return AppStorage(tmp_path / "quota.db", secret_store=EphemeralSecretStore())


def test_daily_quota_blocks_after_limit(tmp_path):
    storage = make_storage(tmp_path)
    quota = SendQuotaService(storage)
    quota.record_sent("acc-1", "a@example.com", task_id=1, sent_at="2026-07-06T09:00:00")
    quota.record_sent("acc-1", "b@example.com", task_id=1, sent_at="2026-07-06T10:00:00")

    allowed = quota.check("acc-1", daily_limit=2, hourly_limit=0, now="2026-07-06T11:00:00")

    assert allowed.allowed is False
    assert allowed.code == "daily_limit_reached"
    assert "每日发送上限" in allowed.message


def test_hourly_quota_uses_rolling_window(tmp_path):
    storage = make_storage(tmp_path)
    quota = SendQuotaService(storage)
    quota.record_sent("acc-1", "old@example.com", task_id=1, sent_at="2026-07-06T09:59:00")
    quota.record_sent("acc-1", "recent@example.com", task_id=1, sent_at="2026-07-06T10:30:00")

    blocked = quota.check("acc-1", daily_limit=0, hourly_limit=1, now="2026-07-06T10:45:00")
    allowed = quota.check("acc-1", daily_limit=0, hourly_limit=1, now="2026-07-06T11:01:00")

    assert blocked.allowed is False
    assert blocked.code == "hourly_limit_reached"
    assert allowed.allowed is True
