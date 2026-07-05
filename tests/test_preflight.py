from app.services.preflight import build_preflight_report
from tests.helpers import make_dataset


def test_build_preflight_report_counts_valid_emails_and_template_gaps():
    dataset = make_dataset(
        [
            {"Email": "ok@example.com", "Company": "Acme", "Name": "Alice"},
            {"Email": "not-an-email", "Company": "Beta", "Name": "Bob"},
            {"Email": "", "Company": "Gamma", "Name": "Cara"},
        ],
        field_mapping={"product": None},
    )

    report = build_preflight_report(
        dataset,
        "Subject: {Company}\n\nHi {Name}, {Product} {UnknownField}",
    )

    assert report.total_rows == 3
    assert report.valid_email_rows == 1
    assert report.missing_email_rows == 2
    assert report.unresolved_placeholders == ["UnknownField"]
    assert report.fallback_placeholders == ["Product"]
    assert report.unmapped_required_fields == ["product"]
    assert report.invalid_email_examples == ["第 2 行: not-an-email", "第 3 行: 空值"]


def test_build_preflight_report_accepts_extractable_email_values():
    dataset = make_dataset(
        [
            {"Email": "Alice <ok@example.com>", "Company": "Acme", "Name": "Alice"},
            {"Email": "mailto:sales@example.com", "Company": "Beta", "Name": "Bob"},
            {"Email": "not-an-email", "Company": "Gamma", "Name": "Cara"},
        ]
    )

    report = build_preflight_report(dataset, "Subject: {Company}\n\nHi {Name}")

    assert report.valid_email_rows == 2
    assert report.missing_email_rows == 1
    assert report.invalid_email_examples == ["第 3 行: not-an-email"]
