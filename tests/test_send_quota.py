import os
import sqlite3
import time

import pytest

from app.services.secret_store import EphemeralSecretStore
from app.services.send_quota import SendQuotaService
from app.storage.db import AppStorage


def make_storage(tmp_path):
    return AppStorage(tmp_path / "quota.db", secret_store=EphemeralSecretStore())


def create_legacy_quota_db(db_path, sent_at: str = "2026-07-06T10:30:00+08:00"):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE send_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                source_file TEXT NOT NULL,
                status TEXT NOT NULL,
                total_count INTEGER NOT NULL,
                dataset_fingerprint TEXT NOT NULL DEFAULT '',
                success_count INTEGER NOT NULL,
                failure_count INTEGER NOT NULL,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                review_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE send_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                row_index INTEGER NOT NULL,
                recipient_email TEXT NOT NULL,
                account_label TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES send_tasks(id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO send_tasks(
                id, label, source_file, status, total_count, dataset_fingerprint,
                success_count, failure_count, skipped_count, review_count,
                created_at, started_at, finished_at
            )
            VALUES(1, 'legacy import', 'legacy.csv', 'completed', 1, '', 1, 0, 0, 0,
                   '2026-07-06T10:00:00', '2026-07-06T10:00:00', '2026-07-06T10:31:00')
            """
        )
        conn.execute(
            """
            INSERT INTO send_results(
                task_id, row_index, recipient_email, account_label, subject, body,
                status, error_message, sent_at
            )
            VALUES(1, 0, 'Buyer@Example.com', 'acc-legacy', 'Hello', 'Body', 'sent', '', ?)
            """,
            (sent_at,),
        )


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


def test_init_backfills_legacy_sent_results_into_account_usage(tmp_path):
    db_path = tmp_path / "quota.db"
    create_legacy_quota_db(db_path)

    storage = AppStorage(db_path, secret_store=EphemeralSecretStore())
    quota = SendQuotaService(storage)

    blocked = quota.check("acc-legacy", daily_limit=1, hourly_limit=0, now="2026-07-06T03:00:00")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT account_label, recipient_email, task_id, sent_at
            FROM account_send_usage
            """
        ).fetchone()

    assert blocked.allowed is False
    assert blocked.code == "daily_limit_reached"
    assert row == ("acc-legacy", "Buyer@Example.com", 1, "2026-07-06T02:30:00")


def test_init_backfills_legacy_naive_sent_at_as_local_time(monkeypatch, tmp_path):
    if not hasattr(time, "tzset"):
        pytest.skip("tzset is required for deterministic local-time migration coverage")
    original_tz = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    time.tzset()
    try:
        db_path = tmp_path / "quota.db"
        create_legacy_quota_db(db_path, sent_at="2026-07-06T10:30:00")

        storage = AppStorage(db_path, secret_store=EphemeralSecretStore())
        quota = SendQuotaService(storage)

        blocked = quota.check("acc-legacy", daily_limit=1, hourly_limit=0, now="2026-07-06T03:00:00")
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT sent_at FROM account_send_usage").fetchone()

        assert blocked.allowed is False
        assert row[0] == "2026-07-06T02:30:00"
    finally:
        if original_tz is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", original_tz)
        time.tzset()


def test_init_backfills_legacy_sent_results_idempotently(tmp_path):
    db_path = tmp_path / "quota.db"
    create_legacy_quota_db(db_path)

    AppStorage(db_path, secret_store=EphemeralSecretStore())
    AppStorage(db_path, secret_store=EphemeralSecretStore())

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM account_send_usage").fetchone()[0]

    assert count == 1


def test_init_skips_legacy_sent_results_with_malformed_sent_at(tmp_path):
    db_path = tmp_path / "quota.db"
    create_legacy_quota_db(db_path, sent_at="not-a-timestamp")

    AppStorage(db_path, secret_store=EphemeralSecretStore())

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM account_send_usage").fetchone()[0]

    assert count == 0
