import sqlite3

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


def test_daily_quota_uses_rolling_24_hour_window(tmp_path):
    storage = make_storage(tmp_path)
    quota = SendQuotaService(storage)
    quota.record_sent("acc-1", "late@example.com", task_id=1, sent_at="2026-07-05T23:30:00")
    quota.record_sent("acc-1", "early@example.com", task_id=1, sent_at="2026-07-06T00:30:00")

    allowed = quota.check("acc-1", daily_limit=2, hourly_limit=0, now="2026-07-06T01:00:00")

    assert allowed.allowed is False
    assert allowed.code == "daily_limit_reached"


def test_hourly_quota_uses_rolling_window(tmp_path):
    storage = make_storage(tmp_path)
    quota = SendQuotaService(storage)
    quota.record_sent("acc-1", "old@example.com", task_id=1, sent_at="2026-07-06T09:30:00")
    quota.record_sent("acc-1", "recent@example.com", task_id=1, sent_at="2026-07-06T10:30:00")

    blocked = quota.check("acc-1", daily_limit=0, hourly_limit=1, now="2026-07-06T10:45:00")
    allowed = quota.check("acc-1", daily_limit=0, hourly_limit=1, now="2026-07-06T11:31:00")

    assert blocked.allowed is False
    assert blocked.code == "hourly_limit_reached"
    assert allowed.allowed is True


def test_future_usage_does_not_count_against_quota(tmp_path):
    storage = make_storage(tmp_path)
    quota = SendQuotaService(storage)
    quota.record_sent("acc-1", "future@example.com", task_id=1, sent_at="2026-07-06T12:00:00")

    allowed = quota.check("acc-1", daily_limit=1, hourly_limit=1, now="2026-07-06T11:00:00")

    assert allowed.allowed is True


def test_storage_normalizes_offset_aware_usage_timestamps(tmp_path):
    storage = make_storage(tmp_path)
    storage.add_account_send_usage(
        "acc-1",
        "buyer@example.com",
        task_id=1,
        sent_at="2026-07-06T10:30:00+08:00",
    )

    count = storage.count_account_usage_between(
        "acc-1",
        "2026-07-06T02:00:00",
        "2026-07-06T03:00:00",
    )

    assert count == 1


def test_storage_stores_usage_timestamps_as_canonical_utc_seconds(tmp_path):
    storage = make_storage(tmp_path)
    storage.add_account_send_usage(
        "acc-1",
        "buyer@example.com",
        task_id=1,
        sent_at="2026-07-06T10:30:00+08:00",
    )

    with sqlite3.connect(storage.db_path) as conn:
        row = conn.execute(
            "SELECT sent_at FROM account_send_usage WHERE account_label = ?",
            ("acc-1",),
        ).fetchone()

    assert row[0] == "2026-07-06T02:30:00"


def test_storage_normalizes_offset_aware_query_bounds(tmp_path):
    storage = make_storage(tmp_path)
    storage.add_account_send_usage(
        "acc-1",
        "buyer@example.com",
        task_id=1,
        sent_at="2026-07-06T02:30:00",
    )

    count = storage.count_account_usage_between(
        "acc-1",
        "2026-07-06T10:00:00+08:00",
        "2026-07-06T11:00:00+08:00",
    )

    assert count == 1


def test_offset_aware_future_usage_does_not_count_against_quota(tmp_path):
    storage = make_storage(tmp_path)
    quota = SendQuotaService(storage)
    quota.record_sent("acc-1", "future@example.com", task_id=1, sent_at="2026-07-06T04:00:00+00:00")

    allowed = quota.check("acc-1", daily_limit=1, hourly_limit=1, now="2026-07-06T11:00:00+08:00")

    assert allowed.allowed is True


def test_offset_aware_hourly_usage_counts_inside_window(tmp_path):
    storage = make_storage(tmp_path)
    quota = SendQuotaService(storage)
    quota.record_sent("acc-1", "recent@example.com", task_id=1, sent_at="2026-07-06T02:30:00+00:00")

    blocked = quota.check("acc-1", daily_limit=0, hourly_limit=1, now="2026-07-06T11:00:00+08:00")

    assert blocked.allowed is False
    assert blocked.code == "hourly_limit_reached"


def test_disabled_limits_allow_even_with_usage(tmp_path):
    storage = make_storage(tmp_path)
    quota = SendQuotaService(storage)
    quota.record_sent("acc-1", "a@example.com", task_id=1, sent_at="2026-07-06T10:00:00")
    quota.record_sent("acc-1", "b@example.com", task_id=1, sent_at="2026-07-06T10:30:00")

    allowed = quota.check("acc-1", daily_limit=0, hourly_limit=0, now="2026-07-06T11:00:00")

    assert allowed.allowed is True


def test_hourly_quota_includes_exact_window_start(tmp_path):
    storage = make_storage(tmp_path)
    quota = SendQuotaService(storage)
    quota.record_sent("acc-1", "boundary@example.com", task_id=1, sent_at="2026-07-06T10:00:00")

    blocked = quota.check("acc-1", daily_limit=0, hourly_limit=1, now="2026-07-06T11:00:00")

    assert blocked.allowed is False
    assert blocked.code == "hourly_limit_reached"
