from app.services.template import (
    extract_placeholders,
    render_template,
    split_subject_and_body,
)
from tests.helpers import make_dataset


def test_extract_placeholders_deduplicates_in_order():
    template = "Subject: Hi {Name}\n\nHello {Name} from {Company} about {Product}."

    assert extract_placeholders(template) == ["Name", "Company", "Product"]


def test_render_template_reports_unresolved_and_fallback_fields():
    dataset = make_dataset(
        [{"Email": "a@example.com", "Company": "Acme"}],
        field_mapping={"name": None, "product": None},
    )
    rendered, issues = render_template(
        "Subject: Hello {Name}\n\n{Company} - {Unknown} - {Product}",
        dataset.rows[0],
        dataset,
    )

    assert "Hello there" in rendered
    assert "{Unknown}" in rendered
    assert issues == ["Unknown", "Name", "Product"]


def test_split_subject_and_body_parses_subject_header():
    subject, body = split_subject_and_body("Subject: Intro\n\nLine 1\nLine 2")

    assert subject == "Intro"
    assert body == "Line 1\nLine 2"
