import threading

from app.services.ai_writer import AISettings, EmailDraft
from app.services.batch_sender import BatchSendSettings, run_batch_send
from app.services.smtp_service import SMTPConfigError
from app.storage.db import AppStorage
from tests.helpers import make_dataset


def make_storage(tmp_path):
    storage = AppStorage(tmp_path / "batch.db")
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


def test_run_batch_send_rotates_accounts_and_records_sent(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset(
        [
            {"Email": "a@example.com", "Company": "A", "Name": "A", "Product": "P"},
            {"Email": "b@example.com", "Company": "B", "Name": "B", "Product": "P"},
            {"Email": "c@example.com", "Company": "C", "Name": "C", "Product": "P"},
        ]
    )
    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    monkeypatch.setattr("app.services.batch_sender.send_email", lambda *args, **kwargs: None)

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="rotation",
        duplicate_policy="send",
        stop_event=threading.Event(),
        settings=BatchSendSettings(),
    )

    results = list(reversed(storage.list_send_results(task_id, limit=10)))
    assert [item["account_label"] for item in results] == ["acc-1", "acc-2", "acc-1"]
    assert {item["status"] for item in results} == {"sent"}


def test_run_batch_send_handles_duplicate_policy_branches(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    prior_task = storage.create_send_task("old", "old.csv", 1)
    storage.add_send_result(
        task_id=prior_task,
        row_index=0,
        recipient_email="dup@example.com",
        account_label="acc-1",
        subject="old",
        body="old",
        status="sent",
    )
    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)

    send_calls = []
    monkeypatch.setattr(
        "app.services.batch_sender.send_email",
        lambda *_args, **_kwargs: send_calls.append("called"),
    )

    review_task = run_batch_send(
        storage=storage,
        dataset=make_dataset([{"Email": "dup@example.com", "Company": "A", "Name": "A", "Product": "P"}]),
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="review",
        duplicate_policy="review",
        stop_event=threading.Event(),
        settings=BatchSendSettings(),
    )
    skip_task = run_batch_send(
        storage=storage,
        dataset=make_dataset([{"Email": "dup@example.com", "Company": "A", "Name": "A", "Product": "P"}]),
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="skip",
        duplicate_policy="skip",
        stop_event=threading.Event(),
        settings=BatchSendSettings(),
    )
    send_task = run_batch_send(
        storage=storage,
        dataset=make_dataset([{"Email": "dup@example.com", "Company": "A", "Name": "A", "Product": "P"}]),
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="send",
        duplicate_policy="send",
        stop_event=threading.Event(),
        settings=BatchSendSettings(),
    )

    assert storage.list_send_results(review_task, limit=1)[0]["status"] == "review_required"
    assert storage.list_send_results(skip_task, limit=1)[0]["status"] == "skipped_duplicate"
    assert storage.list_send_results(send_task, limit=1)[0]["status"] == "sent"
    assert len(send_calls) == 1


def test_run_batch_send_retries_and_then_succeeds(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset([{"Email": "a@example.com", "Company": "A", "Name": "A", "Product": "P"}])
    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    attempts = {"count": 0}

    def flaky_send(*_args, **_kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            try:
                raise TimeoutError("temporary timeout")
            except TimeoutError as exc:
                raise SMTPConfigError("SMTP 发送失败：temporary timeout") from exc

    monkeypatch.setattr("app.services.batch_sender.send_email", flaky_send)

    progress = []
    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="retry-success",
        duplicate_policy="send",
        stop_event=threading.Event(),
        settings=BatchSendSettings(max_retries=1, retry_backoff_seconds=0),
        progress_callback=progress.append,
    )

    assert attempts["count"] == 2
    assert storage.list_send_results(task_id, limit=1)[0]["status"] == "sent"
    assert [item.status for item in progress] == ["attempting", "retrying", "attempting", "sent"]


def test_run_batch_send_retries_and_then_fails(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset([{"Email": "a@example.com", "Company": "A", "Name": "A", "Product": "P"}])
    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)

    def always_fail(*_args, **_kwargs):
        try:
            raise TimeoutError("temporary timeout")
        except TimeoutError as exc:
            raise SMTPConfigError("SMTP 发送失败：temporary timeout") from exc

    monkeypatch.setattr("app.services.batch_sender.send_email", always_fail)

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="retry-fail",
        duplicate_policy="send",
        stop_event=threading.Event(),
        settings=BatchSendSettings(max_retries=1, retry_backoff_seconds=0),
    )

    task = storage.latest_send_task()
    assert task["id"] == str(task_id)
    assert task["status"] == "completed_with_errors"
    assert storage.list_send_results(task_id, limit=1)[0]["status"] == "failed"


def test_run_batch_send_stops_when_stop_event_is_set(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset(
        [
            {"Email": "a@example.com", "Company": "A", "Name": "A", "Product": "P"},
            {"Email": "b@example.com", "Company": "B", "Name": "B", "Product": "P"},
        ]
    )
    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    stop_event = threading.Event()

    def send_once(*_args, **_kwargs):
        stop_event.set()

    monkeypatch.setattr("app.services.batch_sender.send_email", send_once)

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="stopped",
        duplicate_policy="send",
        stop_event=stop_event,
        settings=BatchSendSettings(),
    )

    task = storage.latest_send_task()
    assert task["id"] == str(task_id)
    assert task["status"] == "stopped"
    assert len(storage.list_send_results(task_id, limit=10)) == 1


def test_run_batch_send_normalizes_extractable_email_values(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset(
        [{"Email": "Alice <a@example.com>", "Company": "A", "Name": "A", "Product": "P"}]
    )
    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    send_calls = []

    def capture_send(_config, recipient_email, subject, body, attachment_paths=None):
        send_calls.append(
            {
                "recipient_email": recipient_email,
                "subject": subject,
                "body": body,
            }
        )

    monkeypatch.setattr("app.services.batch_sender.send_email", capture_send)

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="normalized-email",
        duplicate_policy="send",
        stop_event=threading.Event(),
        settings=BatchSendSettings(),
    )

    assert send_calls == [
        {
            "recipient_email": "a@example.com",
            "subject": "Hello",
            "body": "Body",
        }
    ]
    assert storage.list_send_results(task_id, limit=1)[0]["recipient_email"] == "a@example.com"


def test_run_batch_send_passes_attachment_paths(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset([{"Email": "a@example.com", "Company": "A", "Name": "A", "Product": "P"}])
    attachment = tmp_path / "catalog.pdf"
    attachment.write_bytes(b"pdf-data")
    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    send_calls = []

    def capture_send(_config, recipient_email, subject, body, attachment_paths=None):
        send_calls.append(
            {
                "recipient_email": recipient_email,
                "subject": subject,
                "body": body,
                "attachment_paths": attachment_paths,
            }
        )

    monkeypatch.setattr("app.services.batch_sender.send_email", capture_send)

    run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="with-attachments",
        duplicate_policy="send",
        stop_event=threading.Event(),
        attachment_paths=[str(attachment)],
        settings=BatchSendSettings(),
    )

    assert send_calls == [
        {
            "recipient_email": "a@example.com",
            "subject": "Hello",
            "body": "Body",
            "attachment_paths": [str(attachment)],
        }
    ]


def test_run_batch_send_fails_invalid_email_before_draft_or_smtp(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset([{"Email": "not-an-email", "Company": "A", "Name": "A", "Product": "P"}])
    draft_calls = []
    send_calls = []

    def capture_draft(*_args, **_kwargs):
        draft_calls.append("called")
        return stub_draft()

    def capture_send(*_args, **_kwargs):
        send_calls.append("called")

    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", capture_draft)
    monkeypatch.setattr("app.services.batch_sender.send_email", capture_send)

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="invalid-email",
        duplicate_policy="send",
        stop_event=threading.Event(),
        settings=BatchSendSettings(),
    )

    task = storage.latest_send_task()
    result = storage.list_send_results(task_id, limit=1)[0]

    assert task["id"] == str(task_id)
    assert task["status"] == "completed_with_errors"
    assert result["status"] == "failed"
    assert "邮箱为空或格式无效" in result["error_message"]
    assert draft_calls == []
    assert send_calls == []


def test_run_batch_send_uses_bulk_duplicate_lookup_and_still_detects_same_batch_duplicates(
    monkeypatch,
    tmp_path,
):
    storage = make_storage(tmp_path)
    dataset = make_dataset(
        [
            {"Email": "dup@example.com", "Company": "A", "Name": "A", "Product": "P"},
            {"Email": "dup@example.com", "Company": "A", "Name": "A", "Product": "P"},
        ]
    )
    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    monkeypatch.setattr("app.services.batch_sender.send_email", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        storage,
        "count_prior_sent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("run_batch_send should not issue per-row duplicate queries")
        ),
    )

    task_id = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="bulk-dedupe",
        duplicate_policy="review",
        stop_event=threading.Event(),
        settings=BatchSendSettings(),
    )

    results = list(reversed(storage.list_send_results(task_id, limit=10)))
    assert [item["status"] for item in results] == ["sent", "review_required"]


def test_run_batch_send_skips_draft_generation_for_non_send_duplicate_branches(
    monkeypatch,
    tmp_path,
):
    storage = make_storage(tmp_path)
    prior_task = storage.create_send_task("old", "old.csv", 1)
    storage.add_send_result(
        task_id=prior_task,
        row_index=0,
        recipient_email="dup@example.com",
        account_label="acc-1",
        subject="old",
        body="old",
        status="sent",
    )
    draft_calls = []
    monkeypatch.setattr(
        "app.services.batch_sender.generate_email_draft",
        lambda *_args, **_kwargs: draft_calls.append("called") or stub_draft(),
    )
    monkeypatch.setattr(
        "app.services.batch_sender.send_email",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("send_email should not be called")),
    )

    review_task = run_batch_send(
        storage=storage,
        dataset=make_dataset([{"Email": "dup@example.com", "Company": "A", "Name": "A", "Product": "P"}]),
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="review-no-draft",
        duplicate_policy="review",
        stop_event=threading.Event(),
        settings=BatchSendSettings(),
    )
    skip_task = run_batch_send(
        storage=storage,
        dataset=make_dataset([{"Email": "dup@example.com", "Company": "A", "Name": "A", "Product": "P"}]),
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="skip-no-draft",
        duplicate_policy="skip",
        stop_event=threading.Event(),
        settings=BatchSendSettings(),
    )

    assert storage.list_send_results(review_task, limit=1)[0]["status"] == "review_required"
    assert storage.list_send_results(skip_task, limit=1)[0]["status"] == "skipped_duplicate"
    assert draft_calls == []
