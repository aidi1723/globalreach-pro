from app.services.secret_store import EphemeralSecretStore
from app.services.suppression import SuppressionService, parse_suppression_csv
from app.storage.db import AppStorage


def make_storage(tmp_path):
    return AppStorage(tmp_path / "suppression.db", secret_store=EphemeralSecretStore())


def test_suppression_service_normalizes_and_deduplicates_emails(tmp_path):
    storage = make_storage(tmp_path)
    service = SuppressionService(storage)

    first = service.add("Alice <Buyer@Example.COM>", reason="unsubscribe", source="manual")
    second = service.add("buyer@example.com", reason="duplicate", source="manual")

    assert first.recipient_email == "buyer@example.com"
    assert second.recipient_email == "buyer@example.com"
    assert service.is_suppressed("BUYER@example.com") is True
    assert len(service.list_entries()) == 1
    assert service.list_entries()[0].reason == "duplicate"


def test_parse_suppression_csv_reports_invalid_rows():
    imported, invalid = parse_suppression_csv(
        "email,reason\n"
        "ok@example.com,unsubscribe\n"
        "not-an-email,bad\n"
        "Alice <second@example.com>,manual\n"
    )

    assert [item.recipient_email for item in imported] == ["ok@example.com", "second@example.com"]
    assert invalid == ["第 3 行: not-an-email"]


def test_suppression_export_returns_csv_with_header(tmp_path):
    storage = make_storage(tmp_path)
    service = SuppressionService(storage)
    service.add("blocked@example.com", reason="manual block", source="manual")

    exported = service.export_csv()

    assert "recipient_email,reason,source,created_at" in exported
    assert "blocked@example.com,manual block,manual," in exported
