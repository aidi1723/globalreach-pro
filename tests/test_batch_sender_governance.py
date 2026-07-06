import threading
from datetime import datetime, timezone

import pytest

from app.services.ai_writer import AISettings, EmailDraft
from app.services.batch_sender import BatchSendError, BatchSendSettings, GovernanceSettings, run_batch_send
from app.services.secret_store import EphemeralSecretStore
from app.services.smtp_service import SMTPConfigError
from app.services.suppression import SuppressionService
from app.storage.db import AppStorage
from tests.helpers import make_dataset


def make_storage(tmp_path):
    storage = AppStorage(tmp_path / "batch-governance.db", secret_store=EphemeralSecretStore())
    storage.save_smtp_account(
        {
            "label": "acc-1",
            "provider": "custom",
            "sender_email": "one@example.com",
            "sender_name": "One",
            "username": "one",
            "password": "pass",
            "host": "smtp.one.test",
            "port": "465",
            "security": "ssl",
            "dkim_selector": "",
        }
    )
    storage.save_smtp_account(
        {
            "label": "acc-2",
            "provider": "custom",
            "sender_email": "two@example.com",
            "sender_name": "Two",
            "username": "two",
            "password": "pass",
            "host": "smtp.two.test",
            "port": "465",
            "security": "ssl",
            "dkim_selector": "",
        }
    )
    return storage


def stub_draft(*_args, **_kwargs):
    return EmailDraft(subject="Hello", body="Body", source="local-variation", issues=[])


def account_usage_count(storage, account_label):
    return storage.count_account_usage_between(
        account_label,
        "2026-07-01T00:00:00",
        "2026-07-31T23:59:59",
    )


def test_suppressed_recipient_records_suppressed_without_smtp_or_usage(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    SuppressionService(storage).add("blocked@example.com", reason="unsubscribe", source="manual")
    dataset = make_dataset(
        [{"Email": "blocked@example.com", "Company": "A", "Name": "A", "Product": "P"}]
    )
    send_calls = []

    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    monkeypatch.setattr(
        "app.services.batch_sender.send_email",
        lambda *_args, **_kwargs: send_calls.append("called"),
    )

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="suppressed",
        duplicate_policy="send",
        stop_event=threading.Event(),
        governance=GovernanceSettings(quota_now="2026-07-06T11:00:00"),
    )

    result = storage.list_send_results(task_id, limit=1)[0]
    task = storage.latest_send_task()
    assert result["status"] == "suppressed"
    assert result["subject"] == "Hello"
    assert task["status"] == "completed_with_skips"
    assert task["skipped_count"] == "1"
    assert send_calls == []
    assert account_usage_count(storage, "acc-1") == 0


def test_rate_limited_recipient_records_rate_limited_without_smtp_or_new_usage(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    storage.add_account_send_usage(
        "acc-1",
        "prior@example.com",
        task_id=999,
        sent_at="2026-07-06T10:30:00",
    )
    dataset = make_dataset(
        [{"Email": "buyer@example.com", "Company": "A", "Name": "A", "Product": "P"}]
    )
    send_calls = []

    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    monkeypatch.setattr(
        "app.services.batch_sender.send_email",
        lambda *_args, **_kwargs: send_calls.append("called"),
    )

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="rate-limited",
        duplicate_policy="send",
        stop_event=threading.Event(),
        governance=GovernanceSettings(hourly_limit_per_account=1, quota_now="2026-07-06T11:00:00"),
    )

    result = storage.list_send_results(task_id, limit=1)[0]
    task = storage.latest_send_task()
    assert result["status"] == "rate_limited"
    assert "每小时发送上限" in result["error_message"]
    assert task["status"] == "completed_with_skips"
    assert task["skipped_count"] == "1"
    assert send_calls == []
    assert account_usage_count(storage, "acc-1") == 1


def test_successful_send_records_usage_but_suppressed_row_does_not(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    SuppressionService(storage).add("blocked@example.com", reason="unsubscribe", source="manual")
    dataset = make_dataset(
        [
            {"Email": "ok@example.com", "Company": "A", "Name": "A", "Product": "P"},
            {"Email": "blocked@example.com", "Company": "B", "Name": "B", "Product": "P"},
        ]
    )
    send_calls = []

    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)

    def capture_send(_config, recipient_email, *_args, **_kwargs):
        send_calls.append(recipient_email)

    monkeypatch.setattr("app.services.batch_sender.send_email", capture_send)

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="usage",
        duplicate_policy="send",
        stop_event=threading.Event(),
        governance=GovernanceSettings(quota_now="2026-07-06T11:00:00"),
    )

    results = list(reversed(storage.list_send_results(task_id, limit=10)))
    assert [item["status"] for item in results] == ["sent", "suppressed"]
    assert send_calls == ["ok@example.com"]
    assert account_usage_count(storage, "acc-1") == 1
    assert account_usage_count(storage, "acc-2") == 0


def test_successful_send_without_quota_now_does_not_backfill_duplicate_usage(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset(
        [{"Email": "ok@example.com", "Company": "A", "Name": "A", "Product": "P"}]
    )

    class BatchDateTime:
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 7, 6, 11, 0, 0, tzinfo=timezone.utc)
            return value.replace(tzinfo=None) if tz is None else value.astimezone(tz)

    class QuotaDateTime:
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 7, 6, 11, 0, 0, tzinfo=timezone.utc)
            return value if tz is None else value.astimezone(tz)

        @classmethod
        def fromisoformat(cls, value):
            return datetime.fromisoformat(value)

    class StorageDateTime:
        @classmethod
        def now(cls):
            return datetime(2026, 7, 6, 11, 0, 1)

        @classmethod
        def fromisoformat(cls, value):
            return datetime.fromisoformat(value)

    monkeypatch.setattr("app.services.batch_sender.datetime", BatchDateTime)
    monkeypatch.setattr("app.services.send_quota.datetime", QuotaDateTime)
    monkeypatch.setattr("app.storage.db.datetime", StorageDateTime)
    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    monkeypatch.setattr("app.services.batch_sender.send_email", lambda *_args, **_kwargs: None)

    run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="usage-backfill",
        duplicate_policy="send",
        stop_event=threading.Event(),
    )

    reopened = AppStorage(storage.db_path, secret_store=EphemeralSecretStore())

    assert account_usage_count(reopened, "acc-1") == 1


def test_smtp_failure_does_not_record_quota_usage(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset(
        [{"Email": "fail@example.com", "Company": "A", "Name": "A", "Product": "P"}]
    )
    attempts = []

    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)

    def fail_send(_config, recipient_email, *_args, **_kwargs):
        attempts.append(recipient_email)
        raise SMTPConfigError("SMTP 发送失败：authentication failed")

    monkeypatch.setattr("app.services.batch_sender.send_email", fail_send)

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="smtp-failure",
        duplicate_policy="send",
        stop_event=threading.Event(),
        governance=GovernanceSettings(quota_now="2026-07-06T11:00:00"),
    )

    task = storage.latest_send_task()
    result = storage.list_send_results(task_id, limit=1)[0]
    assert task["id"] == str(task_id)
    assert task["status"] == "completed_with_errors"
    assert task["failure_count"] == "1"
    assert result["status"] == "failed"
    assert attempts == ["fail@example.com"]
    assert account_usage_count(storage, "acc-1") == 0


def test_pause_after_first_row_and_resume_sends_only_unrecorded_row(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset(
        [
            {"Email": "first@example.com", "Company": "A", "Name": "A", "Product": "P"},
            {"Email": "second@example.com", "Company": "B", "Name": "B", "Product": "P"},
        ]
    )
    pause_event = threading.Event()
    send_calls = []

    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)

    def pause_after_first_send(_config, recipient_email, *_args, **_kwargs):
        send_calls.append(recipient_email)
        pause_event.set()

    monkeypatch.setattr("app.services.batch_sender.send_email", pause_after_first_send)

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="pause-resume",
        duplicate_policy="send",
        stop_event=threading.Event(),
        pause_event=pause_event,
        governance=GovernanceSettings(quota_now="2026-07-06T11:00:00"),
    )

    task = storage.latest_send_task()
    assert task["id"] == str(task_id)
    assert task["status"] == "paused"
    assert send_calls == ["first@example.com"]
    assert storage.list_recorded_row_indexes(task_id) == {0}

    pause_event.clear()

    def capture_resume_send(_config, recipient_email, *_args, **_kwargs):
        send_calls.append(recipient_email)

    monkeypatch.setattr("app.services.batch_sender.send_email", capture_resume_send)

    resumed_task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="pause-resume",
        duplicate_policy="send",
        stop_event=threading.Event(),
        pause_event=pause_event,
        resume_task_id=task_id,
        governance=GovernanceSettings(quota_now="2026-07-06T11:05:00"),
    )

    task = storage.latest_send_task()
    results = list(reversed(storage.list_send_results(task_id, limit=10)))
    assert resumed_task_id == task_id
    assert task["status"] == "completed"
    assert task["success_count"] == "2"
    assert send_calls == ["first@example.com", "second@example.com"]
    assert [item["row_index"] for item in results] == ["0", "1"]
    assert [item["status"] for item in results] == ["sent", "sent"]
    assert account_usage_count(storage, "acc-1") == 1
    assert account_usage_count(storage, "acc-2") == 1


def test_stop_event_wins_when_stop_and_pause_are_set_after_row(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset(
        [
            {"Email": "first@example.com", "Company": "A", "Name": "A", "Product": "P"},
            {"Email": "second@example.com", "Company": "B", "Name": "B", "Product": "P"},
        ]
    )
    pause_event = threading.Event()
    stop_event = threading.Event()

    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)

    def request_pause_and_stop(_config, *_args, **_kwargs):
        pause_event.set()
        stop_event.set()

    monkeypatch.setattr("app.services.batch_sender.send_email", request_pause_and_stop)

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="stop-over-pause",
        duplicate_policy="send",
        stop_event=stop_event,
        pause_event=pause_event,
        governance=GovernanceSettings(quota_now="2026-07-06T11:00:00"),
    )

    task = storage.get_send_task(task_id)
    assert task["status"] == "stopped"
    assert storage.list_recorded_row_indexes(task_id) == {0}


def test_pause_during_inter_email_delay_stops_before_next_row(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset(
        [
            {"Email": "first@example.com", "Company": "A", "Name": "A", "Product": "P"},
            {"Email": "second@example.com", "Company": "B", "Name": "B", "Product": "P"},
        ]
    )
    stop_event = threading.Event()
    send_calls = []

    class PauseOnThirdCheck:
        def __init__(self):
            self.check_count = 0

        def is_set(self):
            self.check_count += 1
            return self.check_count >= 3

        def set(self):
            self.check_count = 3

        def clear(self):
            self.check_count = 0

    pause_event = PauseOnThirdCheck()

    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    monkeypatch.setattr(stop_event, "wait", lambda _timeout: False)

    def capture_send(_config, recipient_email, *_args, **_kwargs):
        send_calls.append(recipient_email)

    monkeypatch.setattr("app.services.batch_sender.send_email", capture_send)

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="pause-during-delay",
        duplicate_policy="send",
        stop_event=stop_event,
        pause_event=pause_event,
        settings=BatchSendSettings(per_email_delay_seconds=1.0),
        governance=GovernanceSettings(quota_now="2026-07-06T11:00:00"),
    )

    task = storage.get_send_task(task_id)
    assert task["status"] == "paused"
    assert send_calls == ["first@example.com"]
    assert storage.list_recorded_row_indexes(task_id) == {0}


def test_resume_source_mismatch_raises_before_sending(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    task_id = storage.create_send_task("paused", "original.csv", 1)
    storage.update_send_task(task_id, "paused", 0, 0)
    send_calls = []

    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    monkeypatch.setattr(
        "app.services.batch_sender.send_email",
        lambda *_args, **_kwargs: send_calls.append("called"),
    )

    with pytest.raises(BatchSendError, match="恢复任务的名单文件不匹配。"):
        run_batch_send(
            storage=storage,
            dataset=make_dataset(
                [{"Email": "buyer@example.com", "Company": "A", "Name": "A", "Product": "P"}],
                source_path="different.csv",
            ),
            template="Subject: Hello\n\nBody",
            ai_settings=AISettings(),
            task_label="paused",
            duplicate_policy="send",
            stop_event=threading.Event(),
            resume_task_id=task_id,
            governance=GovernanceSettings(quota_now="2026-07-06T11:05:00"),
        )

    assert send_calls == []
    assert storage.get_send_task(task_id)["status"] == "paused"


def test_resume_row_count_mismatch_raises_before_sending(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    task_id = storage.create_send_task("paused", "same.csv", 2)
    storage.update_send_task(task_id, "paused", 0, 0)
    send_calls = []

    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    monkeypatch.setattr(
        "app.services.batch_sender.send_email",
        lambda *_args, **_kwargs: send_calls.append("called"),
    )

    with pytest.raises(BatchSendError, match="恢复任务的名单行数不匹配。"):
        run_batch_send(
            storage=storage,
            dataset=make_dataset(
                [{"Email": "buyer@example.com", "Company": "A", "Name": "A", "Product": "P"}],
                source_path="same.csv",
            ),
            template="Subject: Hello\n\nBody",
            ai_settings=AISettings(),
            task_label="paused",
            duplicate_policy="send",
            stop_event=threading.Event(),
            resume_task_id=task_id,
            governance=GovernanceSettings(quota_now="2026-07-06T11:05:00"),
        )

    assert send_calls == []
    assert storage.get_send_task(task_id)["status"] == "paused"


def test_resume_content_fingerprint_mismatch_raises_before_sending(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    original_dataset = make_dataset(
        [
            {"Email": "first@example.com", "Company": "A", "Name": "A", "Product": "P"},
            {"Email": "second@example.com", "Company": "B", "Name": "B", "Product": "P"},
        ],
        source_path="same.csv",
    )
    pause_event = threading.Event()
    send_calls = []

    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)

    def pause_after_first_send(_config, recipient_email, *_args, **_kwargs):
        send_calls.append(recipient_email)
        pause_event.set()

    monkeypatch.setattr("app.services.batch_sender.send_email", pause_after_first_send)

    task_id = run_batch_send(
        storage=storage,
        dataset=original_dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="fingerprint",
        duplicate_policy="send",
        stop_event=threading.Event(),
        pause_event=pause_event,
        governance=GovernanceSettings(quota_now="2026-07-06T11:00:00"),
    )

    paused_task = storage.get_send_task(task_id)
    assert paused_task["status"] == "paused"
    assert paused_task["dataset_fingerprint"]

    changed_dataset = make_dataset(
        [
            {"Email": "second@example.com", "Company": "B", "Name": "B", "Product": "P"},
            {"Email": "first@example.com", "Company": "A", "Name": "A", "Product": "P"},
        ],
        source_path="same.csv",
    )
    pause_event.clear()

    def capture_resume_send(_config, recipient_email, *_args, **_kwargs):
        send_calls.append(recipient_email)

    monkeypatch.setattr("app.services.batch_sender.send_email", capture_resume_send)

    with pytest.raises(BatchSendError, match="恢复任务的名单内容不匹配。"):
        run_batch_send(
            storage=storage,
            dataset=changed_dataset,
            template="Subject: Hello\n\nBody",
            ai_settings=AISettings(),
            task_label="fingerprint",
            duplicate_policy="send",
            stop_event=threading.Event(),
            pause_event=pause_event,
            resume_task_id=task_id,
            governance=GovernanceSettings(quota_now="2026-07-06T11:05:00"),
        )

    assert send_calls == ["first@example.com"]
    assert storage.get_send_task(task_id)["status"] == "paused"


def test_resume_preserves_existing_mixed_status_counts_and_skips_recorded_rows(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    SuppressionService(storage).add("blocked@example.com", reason="unsubscribe", source="manual")
    dataset = make_dataset(
        [
            {"Email": "blocked@example.com", "Company": "A", "Name": "A", "Product": "P"},
            {"Email": "first@example.com", "Company": "B", "Name": "B", "Product": "P"},
            {"Email": "second@example.com", "Company": "C", "Name": "C", "Product": "P"},
        ]
    )
    pause_event = threading.Event()
    send_calls = []

    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)

    def pause_after_first_send(_config, recipient_email, *_args, **_kwargs):
        send_calls.append(recipient_email)
        pause_event.set()

    monkeypatch.setattr("app.services.batch_sender.send_email", pause_after_first_send)

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="mixed-resume",
        duplicate_policy="send",
        stop_event=threading.Event(),
        pause_event=pause_event,
        governance=GovernanceSettings(quota_now="2026-07-06T11:00:00"),
    )

    paused_task = storage.latest_send_task()
    assert paused_task["status"] == "paused"
    assert paused_task["success_count"] == "1"
    assert paused_task["skipped_count"] == "1"
    assert storage.list_recorded_row_indexes(task_id) == {0, 1}
    assert send_calls == ["first@example.com"]

    pause_event.clear()

    def capture_resume_send(_config, recipient_email, *_args, **_kwargs):
        send_calls.append(recipient_email)

    monkeypatch.setattr("app.services.batch_sender.send_email", capture_resume_send)

    resumed_task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="mixed-resume",
        duplicate_policy="send",
        stop_event=threading.Event(),
        pause_event=pause_event,
        resume_task_id=task_id,
        governance=GovernanceSettings(quota_now="2026-07-06T11:05:00"),
    )

    final_task = storage.latest_send_task()
    results = list(reversed(storage.list_send_results(task_id, limit=10)))
    assert resumed_task_id == task_id
    assert final_task["status"] == "completed_with_skips"
    assert final_task["success_count"] == "2"
    assert final_task["failure_count"] == "0"
    assert final_task["skipped_count"] == "1"
    assert final_task["review_count"] == "0"
    assert send_calls == ["first@example.com", "second@example.com"]
    assert [item["row_index"] for item in results] == ["0", "1", "2"]
    assert [item["status"] for item in results] == ["suppressed", "sent", "sent"]


def test_resume_stopped_task_raises_without_sending(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset(
        [{"Email": "stopped@example.com", "Company": "A", "Name": "A", "Product": "P"}]
    )
    stop_event = threading.Event()
    stop_event.set()
    send_calls = []

    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    monkeypatch.setattr(
        "app.services.batch_sender.send_email",
        lambda *_args, **_kwargs: send_calls.append("called"),
    )

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="stopped",
        duplicate_policy="send",
        stop_event=stop_event,
        governance=GovernanceSettings(quota_now="2026-07-06T11:00:00"),
    )

    assert storage.latest_send_task()["status"] == "stopped"

    with pytest.raises(BatchSendError, match="只有已暂停的任务可以恢复。"):
        run_batch_send(
            storage=storage,
            dataset=dataset,
            template="Subject: Hello\n\nBody",
            ai_settings=AISettings(),
            task_label="stopped",
            duplicate_policy="send",
            stop_event=threading.Event(),
            resume_task_id=task_id,
            governance=GovernanceSettings(quota_now="2026-07-06T11:05:00"),
        )

    assert storage.get_send_task(task_id)["status"] == "stopped"
    assert send_calls == []


def test_resume_completed_task_raises_without_sending(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset(
        [{"Email": "done@example.com", "Company": "A", "Name": "A", "Product": "P"}]
    )
    send_calls = []

    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)

    def capture_send(_config, recipient_email, *_args, **_kwargs):
        send_calls.append(recipient_email)

    monkeypatch.setattr("app.services.batch_sender.send_email", capture_send)

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="completed",
        duplicate_policy="send",
        stop_event=threading.Event(),
        governance=GovernanceSettings(quota_now="2026-07-06T11:00:00"),
    )

    assert storage.latest_send_task()["status"] == "completed"
    send_calls.clear()

    with pytest.raises(BatchSendError, match="只有已暂停的任务可以恢复。"):
        run_batch_send(
            storage=storage,
            dataset=dataset,
            template="Subject: Hello\n\nBody",
            ai_settings=AISettings(),
            task_label="completed",
            duplicate_policy="send",
            stop_event=threading.Event(),
            resume_task_id=task_id,
            governance=GovernanceSettings(quota_now="2026-07-06T11:05:00"),
        )

    assert storage.get_send_task(task_id)["status"] == "completed"
    assert send_calls == []
