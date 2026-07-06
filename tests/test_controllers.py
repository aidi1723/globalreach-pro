import sys
import threading
import types

fake_tkinter = types.ModuleType("tkinter")
fake_tkinter.filedialog = types.SimpleNamespace()
fake_tkinter.messagebox = types.SimpleNamespace()
sys.modules.setdefault("tkinter", fake_tkinter)
sys.modules.setdefault("tkinter.filedialog", fake_tkinter.filedialog)
sys.modules.setdefault("tkinter.messagebox", fake_tkinter.messagebox)

from app.controllers import state_controller, workspace_controller
from app.services.batch_sender import GovernanceSettings
from tests.helpers import make_dataset


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeEntry:
    def __init__(self, value=""):
        self.value = value

    def insert(self, index, value):
        text = str(value)
        if str(index) in {"0", "0.0"}:
            self.value = text + self.value
        else:
            self.value += text

    def delete(self, _start, _end=None):
        self.value = ""

    def get(self):
        return self.value


class FakeTextBox:
    def __init__(self, value=""):
        self.value = value

    def insert(self, index, value):
        text = str(value)
        if str(index) in {"0", "0.0"}:
            self.value = text + self.value
        else:
            self.value += text

    def delete(self, _start, _end=None):
        self.value = ""

    def get(self, _start="0.0", _end="end"):
        return self.value


class FakeLabel:
    def __init__(self):
        self.kwargs = {}

    def configure(self, **kwargs):
        self.kwargs.update(kwargs)


class FakeStorage:
    def __init__(self, values):
        self.values = values

    def get_state(self, key):
        return self.values.get(key)

    def set_state(self, key, value):
        self.values[key] = value


class FakeWorkspaceStorage(FakeStorage):
    def __init__(self, values=None, latest_task=None, task=None):
        super().__init__(values or {})
        self.latest_task = latest_task
        self.task = task

    def latest_send_task(self):
        return self.latest_task

    def get_send_task(self, _task_id):
        return self.task

    def list_smtp_accounts(self):
        return [{"label": "acc-1"}]


class FakeGovernanceStorage(FakeWorkspaceStorage):
    def __init__(self, values=None, latest_task=None):
        super().__init__(values=values or {}, latest_task=latest_task)
        self.suppression_entries = {}

    def upsert_suppression_entry(self, recipient_email, reason, source):
        entry = {
            "recipient_email": recipient_email,
            "reason": reason,
            "source": source,
            "created_at": "2026-07-06T10:00:00",
        }
        self.suppression_entries[recipient_email] = entry
        return entry

    def delete_suppression_entry(self, recipient_email):
        self.suppression_entries.pop(recipient_email, None)

    def get_suppression_entry(self, recipient_email):
        return self.suppression_entries.get(recipient_email)

    def list_suppression_entries(self):
        return list(self.suppression_entries.values())


class FakeStateApp:
    def __init__(self, values):
        self.storage = FakeStorage(values)
        self.ai_mode_var = FakeVar()
        self.ai_tone_var = FakeVar()
        self.ai_model_entry = FakeEntry()
        self.ai_endpoint_entry = FakeEntry()
        self.ai_api_key_entry = FakeEntry()
        self.ai_offer_entry = FakeEntry()
        self.ai_cta_entry = FakeEntry()
        self.ai_signature_entry = FakeEntry()
        self.daily_limit_entry = FakeEntry()
        self.hourly_limit_entry = FakeEntry()

        self.smtp_preset_var = FakeVar()
        self.smtp_security_var = FakeVar()
        self.smtp_host_entry = FakeEntry()
        self.smtp_port_entry = FakeEntry()
        self.smtp_username_entry = FakeEntry()
        self.smtp_password_entry = FakeEntry()
        self.smtp_sender_name_entry = FakeEntry()
        self.smtp_sender_email_entry = FakeEntry()
        self.smtp_dkim_selector_entry = FakeEntry()
        self.smtp_test_recipient_entry = FakeEntry()
        self.smtp_subject_entry = FakeEntry()
        self.smtp_body_box = FakeTextBox()
        self.domain_auth_box = FakeTextBox()
        self.smtp_attachment_paths = []
        self.account_pool_refreshes = 0
        self.attachment_refreshes = 0
        self.advanced_toggles = 0

    def populate_account_pool_menu(self):
        self.account_pool_refreshes += 1

    def refresh_attachment_summary(self):
        self.attachment_refreshes += 1

    def toggle_advanced_smtp_fields(self):
        self.advanced_toggles += 1


class FakePreflightApp:
    def __init__(self, dataset, template):
        self.dataset = dataset
        self.template = template
        self.mapping_box = FakeTextBox()
        self.preflight_box = FakeTextBox()
        self.dataset_stats_label = FakeLabel()
        self.smtp_sender_email_entry = FakeEntry("")
        self.smtp_dkim_selector_entry = FakeEntry("")
        self.refresh_mapping_summary = lambda *args, **kwargs: workspace_controller.refresh_mapping_summary(
            self, *args, **kwargs
        )

    def get_template_text(self):
        return self.template

    def add_log(self, _message, level="INFO"):
        return level


def test_load_ai_state_overwrites_entries_instead_of_appending():
    app = FakeStateApp(
        {
            "ai_mode": "openai",
            "ai_tone": "warm",
            "ai_model": "gpt-test",
            "ai_endpoint": "https://example.test/v1/chat/completions",
            "ai_api_key": "secret",
            "ai_offer_summary": "Offer summary",
            "ai_call_to_action": "Reply for details.",
            "ai_signature_name": "Alice",
        }
    )

    state_controller.load_ai_state(app)
    state_controller.load_ai_state(app)

    assert app.ai_mode_var.get() == "openai"
    assert app.ai_tone_var.get() == "warm"
    assert app.ai_model_entry.get() == "gpt-test"
    assert app.ai_endpoint_entry.get() == "https://example.test/v1/chat/completions"
    assert app.ai_api_key_entry.get() == "secret"
    assert app.ai_offer_entry.get() == "Offer summary"
    assert app.ai_cta_entry.get() == "Reply for details."
    assert app.ai_signature_entry.get() == "Alice"


def test_load_governance_state_defaults_to_zero_and_overwrites_entries():
    app = FakeStateApp({})

    state_controller.load_governance_state(app)
    state_controller.load_governance_state(app)

    assert app.daily_limit_entry.get() == "0"
    assert app.hourly_limit_entry.get() == "0"


def test_load_smtp_state_overwrites_entries_instead_of_appending():
    app = FakeStateApp(
        {
            "smtp_provider": "custom",
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_username": "alice",
            "smtp_password": "secret",
            "smtp_sender_name": "Alice",
            "smtp_sender_email": "alice@example.com",
            "smtp_dkim_selector": "selector1",
            "smtp_security": "starttls",
            "smtp_test_recipient": "bob@example.com",
            "smtp_test_subject": "SMTP Test",
            "smtp_attachment_paths": '["/tmp/catalog.pdf"]',
        }
    )

    state_controller.load_smtp_state(app)
    state_controller.load_smtp_state(app)

    assert app.smtp_host_entry.get() == "smtp.example.com"
    assert app.smtp_port_entry.get() == "587"
    assert app.smtp_username_entry.get() == "alice"
    assert app.smtp_password_entry.get() == "secret"
    assert app.smtp_sender_name_entry.get() == "Alice"
    assert app.smtp_sender_email_entry.get() == "alice@example.com"
    assert app.smtp_dkim_selector_entry.get() == "selector1"
    assert app.smtp_test_recipient_entry.get() == "bob@example.com"
    assert app.smtp_subject_entry.get() == "SMTP Test"
    assert app.smtp_security_var.get() == "starttls"
    assert app.smtp_attachment_paths == ["/tmp/catalog.pdf"]


def test_collect_governance_settings_persists_valid_limits():
    app = types.SimpleNamespace(
        daily_limit_entry=FakeEntry("25"),
        hourly_limit_entry=FakeEntry("5"),
        storage=FakeStorage({}),
    )

    settings = workspace_controller._collect_governance_settings(app)

    assert settings == GovernanceSettings(25, 5)
    assert app.storage.values["daily_limit_per_account"] == "25"
    assert app.storage.values["hourly_limit_per_account"] == "5"


def test_resume_batch_send_rejects_mismatched_loaded_dataset(monkeypatch):
    messagebox_calls = []
    app = types.SimpleNamespace(
        dataset=make_dataset(
            [{"Email": "buyer@example.com", "Company": "A", "Name": "A", "Product": "P"}],
            source_path="loaded.csv",
        ),
        storage=FakeWorkspaceStorage(
            latest_task={
                "id": "123",
                "status": "paused",
                "source_file": "paused.csv",
                "label": "Paused task",
            }
        ),
        send_pause_event=threading.Event(),
        start_calls=[],
    )
    app.start_batch_send = lambda **kwargs: app.start_calls.append(kwargs)

    monkeypatch.setattr(
        workspace_controller.messagebox,
        "showerror",
        lambda title, message: messagebox_calls.append((title, message)),
        raising=False,
    )

    workspace_controller.resume_batch_send(app)

    assert app.start_calls == []
    assert messagebox_calls == [
        (
            "无法恢复任务",
            "当前载入名单与暂停任务来源不一致，请先载入 paused.csv 后再恢复。",
        )
    ]


def test_resume_batch_send_logs_current_settings_warning_before_start():
    logs = []
    app = types.SimpleNamespace(
        dataset=make_dataset(
            [{"Email": "buyer@example.com", "Company": "A", "Name": "A", "Product": "P"}],
            source_path="paused.csv",
        ),
        storage=FakeWorkspaceStorage(
            latest_task={
                "id": "123",
                "status": "paused",
                "source_file": "paused.csv",
                "label": "Paused task",
            }
        ),
        send_pause_event=threading.Event(),
        start_calls=[],
        add_log=lambda message, level="INFO": logs.append((message, level)),
    )
    app.start_batch_send = lambda **kwargs: app.start_calls.append(kwargs)

    workspace_controller.resume_batch_send(app)

    assert app.start_calls == [{"resume_task_id": 123}]
    assert any("恢复任务将使用当前界面的发送设置" in message for message, _level in logs)


def test_stop_batch_send_clears_pause_before_setting_stop():
    pause_event = threading.Event()
    stop_event = threading.Event()
    pause_event.set()
    app = types.SimpleNamespace(
        send_pause_event=pause_event,
        send_stop_event=stop_event,
        logs=[],
        task_status_box=FakeTextBox(),
    )
    app.add_log = lambda message, level="INFO": app.logs.append((message, level))
    app.task_status_box.see = lambda _index: None

    workspace_controller.stop_batch_send(app)

    assert not app.send_pause_event.is_set()
    assert app.send_stop_event.is_set()


def test_start_batch_send_resume_forwards_governance_pause_event_and_resume_id(monkeypatch):
    captured = {}
    pending_threads = []

    class DelayedThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon
            pending_threads.append(self)

        def start(self):
            return None

        def is_alive(self):
            return False

    def fake_run_batch_send(**kwargs):
        captured.update(kwargs)
        return 123

    app = types.SimpleNamespace(
        dataset=make_dataset(
            [{"Email": "buyer@example.com", "Company": "A", "Name": "A", "Product": "P"}],
            source_path="paused.csv",
        ),
        storage=FakeWorkspaceStorage(
            task={
                "id": "123",
                "status": "paused",
                "source_file": "paused.csv",
                "label": "Paused task",
            }
        ),
        send_thread=None,
        send_stop_event=threading.Event(),
        send_pause_event=threading.Event(),
        batch_delay_entry=FakeEntry("0"),
        batch_retries_entry=FakeEntry("1"),
        daily_limit_entry=FakeEntry("25"),
        hourly_limit_entry=FakeEntry("5"),
        dedupe_policy_var=FakeVar("send"),
        smtp_attachment_paths=["catalog.pdf"],
        task_status_box=FakeTextBox(),
        logs=[],
        finish_calls=[],
        error_calls=[],
    )
    app.collect_ai_settings = lambda: types.SimpleNamespace(mode="local")
    app.get_template_text = lambda: "Subject: Hello\n\nBody"
    app.add_log = lambda message, level="INFO": app.logs.append((message, level))
    app.after = lambda _delay, callback: callback()
    app._handle_batch_finish = lambda task_id: app.finish_calls.append(task_id)
    app._handle_batch_error = lambda exc: app.error_calls.append(exc)

    monkeypatch.setattr(workspace_controller.threading, "Thread", DelayedThread)
    monkeypatch.setattr(workspace_controller, "run_batch_send", fake_run_batch_send)

    workspace_controller.start_batch_send(app, resume_task_id=123)

    original_dataset = app.dataset
    original_dataset.field_mapping["email"] = "MutatedEmail"
    original_dataset.mapping_details["email"] = {
        "header": "MutatedEmail",
        "confidence": "manual",
        "reason": "mutated after start",
    }
    original_dataset.rows[0]["Email"] = "mutated@example.com"
    original_dataset.rows.append(
        {"Email": "late@example.com", "Company": "Late", "Name": "Late", "Product": "P"}
    )
    app.dataset = make_dataset(
        [{"Email": "other@example.com", "Company": "B", "Name": "B", "Product": "P"}],
        source_path="other.csv",
    )
    app.dedupe_policy_var.set("review")
    app.smtp_attachment_paths.append("mutated.pdf")

    assert len(pending_threads) == 1
    pending_threads[0].target()

    assert captured["dataset"] is not original_dataset
    assert captured["dataset"].source_path == "paused.csv"
    assert captured["dataset"].field_mapping["email"] == "Email"
    assert captured["dataset"].mapping_details["email"]["header"] == "Email"
    assert captured["dataset"].rows == [
        {"Email": "buyer@example.com", "Company": "A", "Name": "A", "Product": "P"}
    ]
    assert captured["duplicate_policy"] == "send"
    assert captured["attachment_paths"] == ["catalog.pdf"]
    assert captured["governance"] == GovernanceSettings(25, 5)
    assert captured["pause_event"] is app.send_pause_event
    assert captured["resume_task_id"] == 123
    assert captured["task_label"] == "Paused task"
    assert app.finish_calls == [123]
    assert app.error_calls == []


def test_collect_governance_settings_rejects_invalid_limits():
    invalid_apps = [
        types.SimpleNamespace(
            daily_limit_entry=FakeEntry("-1"),
            hourly_limit_entry=FakeEntry("5"),
            storage=FakeStorage({}),
        ),
        types.SimpleNamespace(
            daily_limit_entry=FakeEntry("25"),
            hourly_limit_entry=FakeEntry("abc"),
            storage=FakeStorage({}),
        ),
    ]

    for app in invalid_apps:
        try:
            workspace_controller._collect_governance_settings(app)
        except ValueError as exc:
            assert "发送上限必须是非负整数" in str(exc)
        else:
            raise AssertionError("Expected ValueError for invalid governance limits")


def test_run_preflight_reuses_existing_report_for_mapping_summary(monkeypatch):
    app = FakePreflightApp(
        make_dataset(
            [
                {"Email": "ok@example.com", "Company": "Acme", "Name": "Alice", "Product": "Windows"},
                {"Email": "bad-email", "Company": "Beta", "Name": "Bob", "Product": "Doors"},
            ]
        ),
        "Subject: {Company}\n\nHi {Name}",
    )
    real_build_preflight_report = workspace_controller.build_preflight_report
    calls = {"count": 0}

    def counting_build_preflight_report(dataset, template):
        calls["count"] += 1
        return real_build_preflight_report(dataset, template)

    monkeypatch.setattr(
        workspace_controller,
        "build_preflight_report",
        counting_build_preflight_report,
    )

    workspace_controller.run_preflight(app, silent=True)

    assert calls["count"] == 1
    assert "有效邮箱数: 1" in app.preflight_box.get()
    assert "1 条有效邮箱" in app.dataset_stats_label.kwargs["text"]


def test_refresh_governance_summary_shows_limits_suppression_count_and_latest_task():
    storage = FakeGovernanceStorage(
        latest_task={
            "id": "7",
            "label": "Batch leads 101500",
            "status": "paused",
            "total_count": "5",
        }
    )
    storage.upsert_suppression_entry("blocked@example.com", "unsubscribe", "manual")
    app = types.SimpleNamespace(
        storage=storage,
        dedupe_policy_var=FakeVar("skip"),
        daily_limit_entry=FakeEntry("25"),
        hourly_limit_entry=FakeEntry("5"),
        governance_summary_box=FakeTextBox(),
    )

    workspace_controller.refresh_governance_summary(app)

    summary = app.governance_summary_box.get()
    assert "重复策略: skip" in summary
    assert "每日/账号: 25" in summary
    assert "每小时/账号: 5" in summary
    assert "抑制名单: 1" in summary
    assert "最近任务: paused | Batch leads 101500" in summary


def test_add_suppression_entry_from_ui_saves_and_refreshes(monkeypatch):
    messagebox_calls = []
    app = types.SimpleNamespace(
        storage=FakeGovernanceStorage(),
        suppression_email_entry=FakeEntry(" Buyer <Blocked@Example.com> "),
        suppression_reason_entry=FakeEntry("unsubscribe"),
        suppression_source_entry=FakeEntry("manual"),
        suppression_count_label=FakeLabel(),
        suppression_list_box=FakeTextBox(),
        governance_summary_box=FakeTextBox(),
        dedupe_policy_var=FakeVar("review"),
        daily_limit_entry=FakeEntry("0"),
        hourly_limit_entry=FakeEntry("0"),
        logs=[],
    )
    app.add_log = lambda message, level="INFO": app.logs.append((message, level))
    monkeypatch.setattr(
        workspace_controller.messagebox,
        "showerror",
        lambda title, message: messagebox_calls.append((title, message)),
        raising=False,
    )

    workspace_controller.add_suppression_entry_from_ui(app)

    assert messagebox_calls == []
    assert "blocked@example.com" in app.storage.suppression_entries
    assert app.suppression_email_entry.get() == ""
    assert "抑制名单：1 条" == app.suppression_count_label.kwargs["text"]
    assert "blocked@example.com | unsubscribe | manual" in app.suppression_list_box.get()
    assert "抑制名单: 1" in app.governance_summary_box.get()
    assert any("已加入抑制名单" in message for message, _level in app.logs)


def test_add_suppression_entry_from_ui_rejects_invalid_email(monkeypatch):
    messagebox_calls = []
    app = types.SimpleNamespace(
        storage=FakeGovernanceStorage(),
        suppression_email_entry=FakeEntry("not-an-email"),
        suppression_reason_entry=FakeEntry("unsubscribe"),
        suppression_source_entry=FakeEntry("manual"),
    )
    monkeypatch.setattr(
        workspace_controller.messagebox,
        "showerror",
        lambda title, message: messagebox_calls.append((title, message)),
        raising=False,
    )

    workspace_controller.add_suppression_entry_from_ui(app)

    assert app.storage.suppression_entries == {}
    assert messagebox_calls == [("抑制名单错误", "请输入有效的收件人邮箱。")]


def test_remove_suppression_entry_from_ui_deletes_and_refreshes():
    storage = FakeGovernanceStorage()
    storage.upsert_suppression_entry("blocked@example.com", "unsubscribe", "manual")
    app = types.SimpleNamespace(
        storage=storage,
        suppression_email_entry=FakeEntry("blocked@example.com"),
        suppression_count_label=FakeLabel(),
        suppression_list_box=FakeTextBox(),
        governance_summary_box=FakeTextBox(),
        dedupe_policy_var=FakeVar("review"),
        daily_limit_entry=FakeEntry("0"),
        hourly_limit_entry=FakeEntry("0"),
        logs=[],
    )
    app.add_log = lambda message, level="INFO": app.logs.append((message, level))

    workspace_controller.remove_suppression_entry_from_ui(app)

    assert storage.suppression_entries == {}
    assert app.suppression_email_entry.get() == ""
    assert "抑制名单：0 条" == app.suppression_count_label.kwargs["text"]
    assert "暂无抑制名单记录" in app.suppression_list_box.get()
    assert "抑制名单: 0" in app.governance_summary_box.get()
    assert any("已从抑制名单移除" in message for message, _level in app.logs)
