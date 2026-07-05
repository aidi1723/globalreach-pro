from app.services import ai_writer
from app.services.ai_writer import AISettings, generate_email_draft
from tests.helpers import make_dataset


def test_generate_email_draft_local_mode_is_stable():
    dataset = make_dataset(
        [{"Email": "a@example.com", "Company": "Acme", "Name": "Alice", "Product": "windows"}]
    )
    settings = AISettings(mode="local", tone="professional")
    template = "Subject: Intro\n\nHi {Name},\n\nWe support {Company} on {Product}."

    first = generate_email_draft(template, dataset.rows[0], dataset, 0, settings)
    second = generate_email_draft(template, dataset.rows[0], dataset, 0, settings)

    assert first.subject == second.subject
    assert first.body == second.body
    assert first.source == "local-variation"


def test_generate_email_draft_falls_back_when_remote_ai_fails(monkeypatch):
    dataset = make_dataset(
        [{"Email": "a@example.com", "Company": "Acme", "Name": "Alice", "Product": "windows"}]
    )
    settings = AISettings(
        mode="openai",
        endpoint="https://example.test/v1/chat/completions",
        model="gpt-test",
        api_key="secret",
    )
    template = "Subject: Intro\n\nHi {Name},\n\nWe support {Company} on {Product}."

    def fail_remote(*_args, **_kwargs):
        raise ai_writer.AIWriterError("boom")

    monkeypatch.setattr(ai_writer, "_post_json", fail_remote)

    draft = generate_email_draft(template, dataset.rows[0], dataset, 0, settings)

    assert draft.source == "local-variation"
    assert any("AI 接口失败" in issue for issue in draft.issues)
