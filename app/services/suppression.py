from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from app.services.importer import extract_email_address
from app.storage.db import AppStorage


@dataclass
class SuppressionEntry:
    recipient_email: str
    reason: str
    source: str
    created_at: str = ""


def normalize_recipient_email(value: str) -> str:
    return extract_email_address(value).strip().lower()


def parse_suppression_csv(raw_csv: str) -> tuple[list[SuppressionEntry], list[str]]:
    reader = csv.DictReader(io.StringIO(raw_csv))
    imported_by_email: dict[str, SuppressionEntry] = {}
    invalid: list[str] = []

    for row in reader:
        raw_email = str(row.get("email") or row.get("recipient_email") or "").strip()
        recipient_email = normalize_recipient_email(raw_email)
        if not recipient_email:
            invalid.append(f"第 {reader.line_num} 行: {raw_email}")
            continue

        imported_by_email[recipient_email] = SuppressionEntry(
            recipient_email=recipient_email,
            reason=str(row.get("reason") or "").strip(),
            source=str(row.get("source") or "").strip(),
        )

    return list(imported_by_email.values()), invalid


class SuppressionService:
    def __init__(self, storage: AppStorage):
        self.storage = storage

    def add(self, recipient_email: str, reason: str = "", source: str = "") -> SuppressionEntry:
        normalized_email = normalize_recipient_email(recipient_email)
        if not normalized_email:
            raise ValueError("Invalid recipient email.")

        entry = self.storage.upsert_suppression_entry(
            normalized_email,
            reason.strip(),
            source.strip(),
        )
        return self._entry_from_row(entry)

    def remove(self, recipient_email: str):
        normalized_email = normalize_recipient_email(recipient_email)
        if normalized_email:
            self.storage.delete_suppression_entry(normalized_email)

    def is_suppressed(self, recipient_email: str) -> bool:
        normalized_email = normalize_recipient_email(recipient_email)
        if not normalized_email:
            return False
        return self.storage.get_suppression_entry(normalized_email) is not None

    def list_entries(self) -> list[SuppressionEntry]:
        return [self._entry_from_row(row) for row in self.storage.list_suppression_entries()]

    def import_csv(self, raw_csv: str) -> tuple[list[SuppressionEntry], list[str]]:
        imported, invalid = parse_suppression_csv(raw_csv)
        saved = [
            self.add(entry.recipient_email, reason=entry.reason, source=entry.source)
            for entry in imported
        ]
        return saved, invalid

    def export_csv(self) -> str:
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["recipient_email", "reason", "source", "created_at"],
        )
        writer.writeheader()
        for entry in self.list_entries():
            writer.writerow(
                {
                    "recipient_email": entry.recipient_email,
                    "reason": entry.reason,
                    "source": entry.source,
                    "created_at": entry.created_at,
                }
            )
        return output.getvalue()

    def _entry_from_row(self, row: dict[str, str]) -> SuppressionEntry:
        return SuppressionEntry(
            recipient_email=row["recipient_email"],
            reason=row["reason"],
            source=row["source"],
            created_at=row.get("created_at", ""),
        )
