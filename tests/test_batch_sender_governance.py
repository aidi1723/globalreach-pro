import threading

from app.services.ai_writer import AISettings, EmailDraft
from app.services.batch_sender import GovernanceSettings, run_batch_send
from app.services.secret_store import EphemeralSecretStore
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
