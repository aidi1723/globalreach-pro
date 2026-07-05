import pytest

pytest.importorskip("tkinter", exc_type=ImportError)

from app.controllers import state_controller, workspace_controller
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
