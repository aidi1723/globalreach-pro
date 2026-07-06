# Sending Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add suppression lists, account send limits, row-level send eligibility decisions, and pause/resume support to the desktop batch sender.

**Architecture:** Add focused service modules for suppression, quota, and policy decisions, then have `run_batch_send()` consume those decisions before SMTP delivery. Persist all decisions in existing `send_results` so resume can skip completed rows and the UI can summarize task state without duplicating policy logic.

**Tech Stack:** Python 3.11+, SQLite via `app.storage.db.AppStorage`, pytest, existing CustomTkinter UI/controller pattern.

---

## File Map

- Create `app/services/suppression.py`: normalized suppression-list import/export and lookup service.
- Create `app/services/send_quota.py`: account-level daily/hourly quota service using persisted send usage.
- Create `app/services/send_policy.py`: row eligibility decision service combining email validation, suppression, duplicates, and quotas.
- Modify `app/storage/db.py`: add suppression and usage tables, migration helpers, storage methods, and task resume helpers.
- Modify `app/services/batch_sender.py`: call policy service, record non-send outcomes, record usage after sent mail, and support pause/resume.
- Modify `app/controllers/workspace_controller.py`: collect governance settings, expose pause/resume handlers, and show new counts.
- Modify `app/controllers/state_controller.py`: persist governance settings.
- Modify `app/ui/builders.py`: add compact governance controls in the existing workflow.
- Create `tests/test_suppression.py`: suppression normalization, import/export, and storage behavior.
- Create `tests/test_send_quota.py`: daily/hourly quota boundaries and usage recording.
- Create `tests/test_send_policy.py`: policy decision branches.
- Create `tests/test_batch_sender_governance.py`: integration coverage for suppression, rate limits, pause/resume, and no duplicate sends.
- Modify `tests/test_controllers.py`: controller-level governance state and pause/resume tests.
- Modify `README.md` and `MAINTENANCE.md`: document governance behavior and verification.

---

### Task 1: Suppression Storage and Service

**Files:**
- Create: `app/services/suppression.py`
- Modify: `app/storage/db.py`
- Test: `tests/test_suppression.py`

- [ ] **Step 1: Write failing suppression storage tests**

Add `tests/test_suppression.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_suppression.py -q
```

Expected: fail during import with `ModuleNotFoundError: No module named 'app.services.suppression'`.

- [ ] **Step 3: Add storage methods and migration**

Modify `app/storage/db.py` inside `_init_db()` after `send_results` creation:

```python
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS suppression_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipient_email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    reason TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_suppression_entries_email
                ON suppression_entries(recipient_email COLLATE NOCASE)
                """
            )
```

Add methods near the existing storage methods:

```python
    def upsert_suppression_entry(self, recipient_email: str, reason: str, source: str) -> dict[str, str]:
        now = datetime.now().isoformat(timespec="seconds")
        normalized_email = recipient_email.strip().lower()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO suppression_entries(recipient_email, reason, source, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(recipient_email) DO UPDATE SET
                    reason = excluded.reason,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (normalized_email, reason.strip(), source.strip(), now, now),
            )
            row = conn.execute(
                """
                SELECT recipient_email, reason, source, created_at
                FROM suppression_entries
                WHERE recipient_email = ? COLLATE NOCASE
                """,
                (normalized_email,),
            ).fetchone()
        return {
            "recipient_email": row[0],
            "reason": row[1],
            "source": row[2],
            "created_at": row[3],
        }

    def delete_suppression_entry(self, recipient_email: str):
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM suppression_entries WHERE recipient_email = ? COLLATE NOCASE",
                (recipient_email.strip().lower(),),
            )

    def get_suppression_entry(self, recipient_email: str) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT recipient_email, reason, source, created_at
                FROM suppression_entries
                WHERE recipient_email = ? COLLATE NOCASE
                """,
                (recipient_email.strip().lower(),),
            ).fetchone()
        if not row:
            return None
        return {
            "recipient_email": row[0],
            "reason": row[1],
            "source": row[2],
            "created_at": row[3],
        }

    def list_suppression_entries(self) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT recipient_email, reason, source, created_at
                FROM suppression_entries
                ORDER BY recipient_email COLLATE NOCASE ASC
                """
            ).fetchall()
        return [
            {
                "recipient_email": row[0],
                "reason": row[1],
                "source": row[2],
                "created_at": row[3],
            }
            for row in rows
        ]
```

- [ ] **Step 4: Add suppression service**

Create `app/services/suppression.py`:

```python
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
    imported: list[SuppressionEntry] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for row_number, row in enumerate(reader, start=2):
        raw_email = str(row.get("email") or row.get("recipient_email") or "").strip()
        normalized = normalize_recipient_email(raw_email)
        if not normalized:
            invalid.append(f"第 {row_number} 行: {raw_email or '空值'}")
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        imported.append(
            SuppressionEntry(
                recipient_email=normalized,
                reason=str(row.get("reason") or "suppressed").strip() or "suppressed",
                source=str(row.get("source") or "csv").strip() or "csv",
            )
        )
    return imported, invalid


class SuppressionService:
    def __init__(self, storage: AppStorage):
        self.storage = storage

    def add(self, recipient_email: str, reason: str = "suppressed", source: str = "manual") -> SuppressionEntry:
        normalized = normalize_recipient_email(recipient_email)
        if not normalized:
            raise ValueError("请输入有效邮箱。")
        row = self.storage.upsert_suppression_entry(normalized, reason, source)
        return SuppressionEntry(**row)

    def remove(self, recipient_email: str) -> None:
        normalized = normalize_recipient_email(recipient_email)
        if normalized:
            self.storage.delete_suppression_entry(normalized)

    def is_suppressed(self, recipient_email: str) -> bool:
        normalized = normalize_recipient_email(recipient_email)
        return bool(normalized and self.storage.get_suppression_entry(normalized))

    def list_entries(self) -> list[SuppressionEntry]:
        return [SuppressionEntry(**row) for row in self.storage.list_suppression_entries()]

    def import_csv(self, raw_csv: str) -> tuple[int, list[str]]:
        entries, invalid = parse_suppression_csv(raw_csv)
        for entry in entries:
            self.storage.upsert_suppression_entry(entry.recipient_email, entry.reason, entry.source)
        return len(entries), invalid

    def export_csv(self) -> str:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["recipient_email", "reason", "source", "created_at"])
        writer.writeheader()
        for entry in self.list_entries():
            writer.writerow(entry.__dict__)
        return output.getvalue()
```

- [ ] **Step 5: Run suppression tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_suppression.py -q
```

Expected: `3 passed`.

- [ ] **Step 6: Commit Task 1**

```bash
git add app/storage/db.py app/services/suppression.py tests/test_suppression.py
git commit -m "Add suppression list storage"
```

---

### Task 2: Account Send Quota Service

**Files:**
- Create: `app/services/send_quota.py`
- Modify: `app/storage/db.py`
- Test: `tests/test_send_quota.py`

- [ ] **Step 1: Write failing quota tests**

Create `tests/test_send_quota.py`:

```python
from app.services.secret_store import EphemeralSecretStore
from app.services.send_quota import SendQuotaService
from app.storage.db import AppStorage


def make_storage(tmp_path):
    return AppStorage(tmp_path / "quota.db", secret_store=EphemeralSecretStore())


def test_daily_quota_blocks_after_limit(tmp_path):
    storage = make_storage(tmp_path)
    quota = SendQuotaService(storage)
    quota.record_sent("acc-1", "a@example.com", task_id=1, sent_at="2026-07-06T09:00:00")
    quota.record_sent("acc-1", "b@example.com", task_id=1, sent_at="2026-07-06T10:00:00")

    allowed = quota.check("acc-1", daily_limit=2, hourly_limit=0, now="2026-07-06T11:00:00")

    assert allowed.allowed is False
    assert allowed.code == "daily_limit_reached"
    assert "每日发送上限" in allowed.message


def test_hourly_quota_uses_rolling_window(tmp_path):
    storage = make_storage(tmp_path)
    quota = SendQuotaService(storage)
    quota.record_sent("acc-1", "old@example.com", task_id=1, sent_at="2026-07-06T09:59:00")
    quota.record_sent("acc-1", "recent@example.com", task_id=1, sent_at="2026-07-06T10:30:00")

    blocked = quota.check("acc-1", daily_limit=0, hourly_limit=1, now="2026-07-06T10:45:00")
    allowed = quota.check("acc-1", daily_limit=0, hourly_limit=1, now="2026-07-06T11:01:00")

    assert blocked.allowed is False
    assert blocked.code == "hourly_limit_reached"
    assert allowed.allowed is True
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_send_quota.py -q
```

Expected: fail during import with `ModuleNotFoundError: No module named 'app.services.send_quota'`.

- [ ] **Step 3: Add quota usage storage**

Modify `app/storage/db.py` inside `_init_db()` after `suppression_entries`:

```python
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS account_send_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_label TEXT NOT NULL,
                    recipient_email TEXT NOT NULL,
                    task_id INTEGER NOT NULL,
                    sent_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_account_send_usage_account_sent_at
                ON account_send_usage(account_label, sent_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_account_send_usage_recipient
                ON account_send_usage(recipient_email COLLATE NOCASE)
                """
            )
```

Add storage methods:

```python
    def add_account_send_usage(self, account_label: str, recipient_email: str, task_id: int, sent_at: str):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO account_send_usage(account_label, recipient_email, task_id, sent_at)
                VALUES(?, ?, ?, ?)
                """,
                (account_label, recipient_email.strip().lower(), task_id, sent_at),
            )

    def count_account_usage_since(self, account_label: str, since: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM account_send_usage
                WHERE account_label = ?
                  AND sent_at >= ?
                """,
                (account_label, since),
            ).fetchone()
        return int(row[0]) if row else 0
```

- [ ] **Step 4: Add quota service**

Create `app/services/send_quota.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.storage.db import AppStorage


@dataclass
class QuotaDecision:
    allowed: bool
    code: str = ""
    message: str = ""


def _parse_now(now: str | None = None) -> datetime:
    if now:
        return datetime.fromisoformat(now)
    return datetime.now()


class SendQuotaService:
    def __init__(self, storage: AppStorage):
        self.storage = storage

    def check(self, account_label: str, daily_limit: int = 0, hourly_limit: int = 0, now: str | None = None) -> QuotaDecision:
        current = _parse_now(now)
        if daily_limit > 0:
            day_start = current.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
            daily_count = self.storage.count_account_usage_since(account_label, day_start)
            if daily_count >= daily_limit:
                return QuotaDecision(False, "daily_limit_reached", f"{account_label} 已达到每日发送上限 {daily_limit}。")
        if hourly_limit > 0:
            hour_start = (current - timedelta(hours=1)).isoformat(timespec="seconds")
            hourly_count = self.storage.count_account_usage_since(account_label, hour_start)
            if hourly_count >= hourly_limit:
                return QuotaDecision(False, "hourly_limit_reached", f"{account_label} 已达到每小时发送上限 {hourly_limit}。")
        return QuotaDecision(True)

    def record_sent(self, account_label: str, recipient_email: str, task_id: int, sent_at: str | None = None) -> None:
        timestamp = sent_at or datetime.now().isoformat(timespec="seconds")
        self.storage.add_account_send_usage(account_label, recipient_email, task_id, timestamp)
```

- [ ] **Step 5: Run quota tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_send_quota.py -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit Task 2**

```bash
git add app/storage/db.py app/services/send_quota.py tests/test_send_quota.py
git commit -m "Add account send quota service"
```

---

### Task 3: Send Policy Decision Service

**Files:**
- Create: `app/services/send_policy.py`
- Test: `tests/test_send_policy.py`

- [ ] **Step 1: Write failing policy tests**

Create `tests/test_send_policy.py`:

```python
from app.services.secret_store import EphemeralSecretStore
from app.services.send_policy import SendPolicyService
from app.services.send_quota import SendQuotaService
from app.services.suppression import SuppressionService
from app.storage.db import AppStorage


def make_services(tmp_path):
    storage = AppStorage(tmp_path / "policy.db", secret_store=EphemeralSecretStore())
    suppression = SuppressionService(storage)
    quota = SendQuotaService(storage)
    policy = SendPolicyService(storage, suppression, quota)
    return storage, suppression, quota, policy


def test_policy_blocks_suppressed_recipient(tmp_path):
    _storage, suppression, _quota, policy = make_services(tmp_path)
    suppression.add("blocked@example.com", reason="unsubscribe", source="manual")

    decision = policy.evaluate(
        recipient_email="blocked@example.com",
        duplicate_count=0,
        duplicate_policy="send",
        account_label="acc-1",
        daily_limit=0,
        hourly_limit=0,
    )

    assert decision.status == "suppressed"
    assert decision.should_send is False
    assert "suppression" in decision.code


def test_policy_handles_duplicate_review_and_skip(tmp_path):
    _storage, _suppression, _quota, policy = make_services(tmp_path)

    review = policy.evaluate("dup@example.com", 2, "review", "acc-1", 0, 0)
    skip = policy.evaluate("dup@example.com", 2, "skip", "acc-1", 0, 0)
    send = policy.evaluate("dup@example.com", 2, "send", "acc-1", 0, 0)

    assert review.status == "review_required"
    assert skip.status == "skipped_duplicate"
    assert send.status == "send"
    assert send.should_send is True


def test_policy_blocks_rate_limited_account(tmp_path):
    _storage, _suppression, quota, policy = make_services(tmp_path)
    quota.record_sent("acc-1", "sent@example.com", task_id=1, sent_at="2026-07-06T08:00:00")

    decision = policy.evaluate(
        recipient_email="new@example.com",
        duplicate_count=0,
        duplicate_policy="send",
        account_label="acc-1",
        daily_limit=1,
        hourly_limit=0,
        now="2026-07-06T09:00:00",
    )

    assert decision.status == "rate_limited"
    assert decision.should_send is False
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_send_policy.py -q
```

Expected: fail during import with `ModuleNotFoundError: No module named 'app.services.send_policy'`.

- [ ] **Step 3: Add policy service**

Create `app/services/send_policy.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from app.services.send_quota import SendQuotaService
from app.services.suppression import SuppressionService
from app.storage.db import AppStorage


@dataclass
class SendDecision:
    status: str
    should_send: bool
    code: str = ""
    message: str = ""


class SendPolicyService:
    def __init__(self, storage: AppStorage, suppression: SuppressionService, quota: SendQuotaService):
        self.storage = storage
        self.suppression = suppression
        self.quota = quota

    def evaluate(
        self,
        recipient_email: str,
        duplicate_count: int,
        duplicate_policy: str,
        account_label: str,
        daily_limit: int,
        hourly_limit: int,
        now: str | None = None,
    ) -> SendDecision:
        if not recipient_email:
            return SendDecision("failed", False, "invalid_email", "收件邮箱为空或格式无效。")
        if self.suppression.is_suppressed(recipient_email):
            return SendDecision("suppressed", False, "suppression_match", "该邮箱在 suppression list 中，已阻止发送。")
        if duplicate_count > 0 and duplicate_policy == "review":
            return SendDecision("review_required", False, "duplicate_review", f"该邮箱历史已发送 {duplicate_count} 次，等待人工审核")
        if duplicate_count > 0 and duplicate_policy == "skip":
            return SendDecision("skipped_duplicate", False, "duplicate_skip", f"该邮箱历史已发送 {duplicate_count} 次，按策略自动忽略")
        quota_decision = self.quota.check(account_label, daily_limit=daily_limit, hourly_limit=hourly_limit, now=now)
        if not quota_decision.allowed:
            return SendDecision("rate_limited", False, quota_decision.code, quota_decision.message)
        return SendDecision("send", True)
```

- [ ] **Step 4: Run policy tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_send_policy.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit Task 3**

```bash
git add app/services/send_policy.py tests/test_send_policy.py
git commit -m "Add send policy decisions"
```

---

### Task 4: Batch Sender Governance Integration

**Files:**
- Modify: `app/storage/db.py`
- Modify: `app/services/batch_sender.py`
- Test: `tests/test_batch_sender_governance.py`

- [ ] **Step 1: Write failing batch governance tests**

Create `tests/test_batch_sender_governance.py`:

```python
import threading

from app.services.ai_writer import AISettings, EmailDraft
from app.services.batch_sender import BatchSendSettings, GovernanceSettings, run_batch_send
from app.services.secret_store import EphemeralSecretStore
from app.services.suppression import SuppressionService
from app.storage.db import AppStorage
from tests.helpers import make_dataset


def make_storage(tmp_path):
    storage = AppStorage(tmp_path / "governance.db", secret_store=EphemeralSecretStore())
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
    return storage


def stub_draft(*_args, **_kwargs):
    return EmailDraft(subject="Hello", body="Body", source="local-variation", issues=[])


def test_batch_sender_records_suppressed_without_smtp(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    SuppressionService(storage).add("blocked@example.com", reason="unsubscribe", source="manual")
    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    send_calls = []
    monkeypatch.setattr("app.services.batch_sender.send_email", lambda *_args, **_kwargs: send_calls.append("called"))

    task_id = run_batch_send(
        storage=storage,
        dataset=make_dataset([{"Email": "blocked@example.com", "Company": "A", "Name": "A", "Product": "P"}]),
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="suppressed",
        duplicate_policy="send",
        stop_event=threading.Event(),
        settings=BatchSendSettings(),
        governance=GovernanceSettings(),
    )

    result = storage.list_send_results(task_id, limit=1)[0]
    assert result["status"] == "suppressed"
    assert send_calls == []


def test_batch_sender_records_rate_limited_without_smtp(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    storage.add_account_send_usage("acc-1", "old@example.com", task_id=1, sent_at="2026-07-06T08:00:00")
    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    send_calls = []
    monkeypatch.setattr("app.services.batch_sender.send_email", lambda *_args, **_kwargs: send_calls.append("called"))

    task_id = run_batch_send(
        storage=storage,
        dataset=make_dataset([{"Email": "new@example.com", "Company": "A", "Name": "A", "Product": "P"}]),
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="rate-limited",
        duplicate_policy="send",
        stop_event=threading.Event(),
        settings=BatchSendSettings(),
        governance=GovernanceSettings(daily_limit_per_account=1, quota_now="2026-07-06T09:00:00"),
    )

    result = storage.list_send_results(task_id, limit=1)[0]
    assert result["status"] == "rate_limited"
    assert send_calls == []


def test_batch_sender_pauses_and_resume_skips_completed_rows(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)
    dataset = make_dataset(
        [
            {"Email": "a@example.com", "Company": "A", "Name": "A", "Product": "P"},
            {"Email": "b@example.com", "Company": "B", "Name": "B", "Product": "P"},
        ]
    )
    monkeypatch.setattr("app.services.batch_sender.generate_email_draft", stub_draft)
    send_calls = []
    pause_event = threading.Event()

    def send_and_pause(_config, recipient_email, **_kwargs):
        send_calls.append(recipient_email)
        pause_event.set()

    monkeypatch.setattr("app.services.batch_sender.send_email", send_and_pause)

    paused_task = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="pause",
        duplicate_policy="send",
        stop_event=threading.Event(),
        pause_event=pause_event,
        settings=BatchSendSettings(),
        governance=GovernanceSettings(),
    )

    assert storage.latest_send_task()["status"] == "paused"
    assert send_calls == ["a@example.com"]

    pause_event.clear()
    resumed_task = run_batch_send(
        storage=storage,
        dataset=dataset,
        template="Subject: Hello\n\nBody",
        ai_settings=AISettings(),
        task_label="pause",
        duplicate_policy="send",
        stop_event=threading.Event(),
        pause_event=pause_event,
        settings=BatchSendSettings(),
        governance=GovernanceSettings(),
        resume_task_id=paused_task,
    )

    assert resumed_task == paused_task
    assert send_calls == ["a@example.com", "b@example.com"]
    assert storage.latest_send_task()["status"] == "completed"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_batch_sender_governance.py -q
```

Expected: fail importing `GovernanceSettings` from `app.services.batch_sender`.

- [ ] **Step 3: Add resume storage helpers**

Modify `app/storage/db.py`:

```python
    def get_send_task(self, task_id: int) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, label, source_file, status, total_count, success_count, failure_count,
                       skipped_count, review_count, created_at, started_at, finished_at
                FROM send_tasks
                WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "label": row[1],
            "source_file": row[2],
            "status": row[3],
            "total_count": str(row[4]),
            "success_count": str(row[5]),
            "failure_count": str(row[6]),
            "skipped_count": str(row[7]),
            "review_count": str(row[8]),
            "created_at": row[9],
            "started_at": row[10],
            "finished_at": row[11],
        }

    def list_recorded_row_indexes(self, task_id: int) -> set[int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT row_index FROM send_results WHERE task_id = ?",
                (task_id,),
            ).fetchall()
        return {int(row[0]) for row in rows}
```

- [ ] **Step 4: Add governance settings and policy integration**

Modify `app/services/batch_sender.py` imports:

```python
from app.services.send_policy import SendPolicyService
from app.services.send_quota import SendQuotaService
from app.services.suppression import SuppressionService
```

Add dataclass after `BatchSendSettings`:

```python
@dataclass
class GovernanceSettings:
    daily_limit_per_account: int = 0
    hourly_limit_per_account: int = 0
    quota_now: str | None = None
```

Change `run_batch_send()` signature:

```python
    governance: GovernanceSettings | None = None,
    pause_event=None,
    resume_task_id: int | None = None,
) -> int:
```

At the start of `run_batch_send()` after settings:

```python
    governance = governance or GovernanceSettings()
    quota_service = SendQuotaService(storage)
    policy_service = SendPolicyService(storage, SuppressionService(storage), quota_service)
```

Replace task creation with resume support:

```python
    if resume_task_id is not None:
        existing_task = storage.get_send_task(resume_task_id)
        if not existing_task:
            raise BatchSendError("要恢复的任务不存在。")
        task_id = resume_task_id
        recorded_rows = storage.list_recorded_row_indexes(task_id)
    else:
        task_id = storage.create_send_task(task_label, dataset.source_path, dataset.total_rows)
        recorded_rows = set()
```

At the top of the row loop after stop check:

```python
        if index in recorded_rows:
            continue
```

Before draft generation, replace duplicate-only branching with policy:

```python
            decision = policy_service.evaluate(
                recipient_email=recipient_email,
                duplicate_count=duplicate_count,
                duplicate_policy=duplicate_policy,
                account_label=account.label,
                daily_limit=governance.daily_limit_per_account,
                hourly_limit=governance.hourly_limit_per_account,
                now=governance.quota_now,
            )
            if not decision.should_send:
                status = decision.status
                error_message = decision.message
                if status == "review_required":
                    review_count += 1
                elif status in {"skipped_duplicate", "suppressed", "rate_limited"}:
                    skipped_count += 1
```

After successful `send_email()`:

```python
                    quota_service.record_sent(account.label, recipient_email, task_id)
```

After recording progress and before delay:

```python
        if pause_event is not None and pause_event.is_set():
            storage.update_send_task(
                task_id,
                "paused",
                success_count,
                failure_count,
                skipped_count=skipped_count,
                review_count=review_count,
            )
            return task_id
```

- [ ] **Step 5: Run batch governance tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_batch_sender_governance.py -q
```

Expected: `3 passed`.

- [ ] **Step 6: Run existing batch tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_batch_sender.py -q
```

Expected: all existing batch tests pass.

- [ ] **Step 7: Commit Task 4**

```bash
git add app/storage/db.py app/services/batch_sender.py tests/test_batch_sender_governance.py
git commit -m "Integrate send governance into batch sender"
```

---

### Task 5: Desktop Controller and UI Controls

**Files:**
- Modify: `app/constants.py`
- Modify: `app/controllers/state_controller.py`
- Modify: `app/controllers/workspace_controller.py`
- Modify: `app/ui/builders.py`
- Test: `tests/test_controllers.py`

- [ ] **Step 1: Write failing controller tests**

Append to `tests/test_controllers.py`:

```python
def test_collect_governance_settings_validates_limits():
    app = type("FakeApp", (), {})()
    app.daily_limit_entry = FakeEntry("25")
    app.hourly_limit_entry = FakeEntry("5")

    settings = workspace_controller._collect_governance_settings(app)

    assert settings.daily_limit_per_account == 25
    assert settings.hourly_limit_per_account == 5


def test_collect_governance_settings_rejects_negative_limits():
    app = type("FakeApp", (), {})()
    app.daily_limit_entry = FakeEntry("-1")
    app.hourly_limit_entry = FakeEntry("0")

    try:
        workspace_controller._collect_governance_settings(app)
    except ValueError as exc:
        assert "发送上限必须是非负整数" in str(exc)
    else:
        raise AssertionError("negative limits should fail")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_controllers.py::test_collect_governance_settings_validates_limits tests/test_controllers.py::test_collect_governance_settings_rejects_negative_limits -q
```

Expected: fail with `AttributeError: module 'app.controllers.workspace_controller' has no attribute '_collect_governance_settings'`.

- [ ] **Step 3: Add constants and state loading**

Modify `app/constants.py`:

```python
GOVERNANCE_STATE_KEYS = [
    "daily_limit_per_account",
    "hourly_limit_per_account",
]
```

Modify `app/controllers/state_controller.py` imports:

```python
    GOVERNANCE_STATE_KEYS,
```

Add:

```python
def load_governance_state(app):
    state = {key: app.storage.get_state(key) or "" for key in GOVERNANCE_STATE_KEYS}
    app._set_entry_value(app.daily_limit_entry, state.get("daily_limit_per_account", "") or "0")
    app._set_entry_value(app.hourly_limit_entry, state.get("hourly_limit_per_account", "") or "0")
```

Call `load_governance_state(app)` from `load_persisted_state()` after `load_batch_state(app)`.

- [ ] **Step 4: Add controller helper and pause/resume actions**

Modify `app/controllers/workspace_controller.py` imports:

```python
    GovernanceSettings,
```

Add near `_collect_batch_settings()`:

```python
def _collect_governance_settings(app) -> GovernanceSettings:
    daily_value = app.daily_limit_entry.get().strip() or "0"
    hourly_value = app.hourly_limit_entry.get().strip() or "0"
    if not daily_value.isdigit() or not hourly_value.isdigit():
        raise ValueError("发送上限必须是非负整数。")
    daily_limit = int(daily_value)
    hourly_limit = int(hourly_value)
    app.storage.set_state("daily_limit_per_account", str(daily_limit))
    app.storage.set_state("hourly_limit_per_account", str(hourly_limit))
    return GovernanceSettings(
        daily_limit_per_account=daily_limit,
        hourly_limit_per_account=hourly_limit,
    )
```

In `start_batch_send()`, collect governance settings after `_collect_batch_settings(app)`:

```python
        governance_settings = _collect_governance_settings(app)
```

Pass to `run_batch_send()`:

```python
                governance=governance_settings,
                pause_event=app.send_pause_event,
```

Add actions:

```python
def pause_batch_send(app):
    app.send_pause_event.set()
    app.add_log("已请求暂停当前批量发送任务。", level="WARN")
    app.task_status_box.insert("end", "已请求暂停任务，等待当前发送完成...\n")
    app.task_status_box.see("end")


def resume_batch_send(app):
    task = app.storage.latest_send_task()
    if not task or task["status"] != "paused":
        messagebox.showinfo("提示", "当前没有可恢复的暂停任务。")
        return
    app.send_pause_event.clear()
    app.start_batch_send(resume_task_id=int(task["id"]))
```

Also update `start_batch_send(app, resume_task_id=None)` to accept the optional resume ID and forward it.

- [ ] **Step 5: Add UI controls**

Modify `app/ui/builders.py` inside the existing batch/send control area:

```python
    governance_frame = ctk.CTkFrame(parent)
    governance_frame.pack(fill="x", padx=12, pady=(8, 8))
    ctk.CTkLabel(governance_frame, text="发送治理", font=("Arial", 13, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(8, 4))
    ctk.CTkLabel(governance_frame, text="每日/账号").grid(row=1, column=0, sticky="w", padx=10, pady=4)
    app.daily_limit_entry = ctk.CTkEntry(governance_frame, width=90)
    app.daily_limit_entry.grid(row=1, column=1, sticky="w", padx=6, pady=4)
    ctk.CTkLabel(governance_frame, text="每小时/账号").grid(row=1, column=2, sticky="w", padx=10, pady=4)
    app.hourly_limit_entry = ctk.CTkEntry(governance_frame, width=90)
    app.hourly_limit_entry.grid(row=1, column=3, sticky="w", padx=6, pady=4)
```

Add Pause and Resume buttons near the existing stop button:

```python
    app.pause_send_button = ctk.CTkButton(actions_frame, text="暂停", command=app.pause_batch_send)
    app.pause_send_button.pack(side="left", padx=6)
    app.resume_send_button = ctk.CTkButton(actions_frame, text="恢复", command=app.resume_batch_send)
    app.resume_send_button.pack(side="left", padx=6)
```

- [ ] **Step 6: Wire main class attributes**

Modify `main.py`:

```python
from app.controllers.workspace_controller import (
    pause_batch_send,
    resume_batch_send,
)
```

Add class bindings:

```python
    pause_batch_send = pause_batch_send
    resume_batch_send = resume_batch_send
```

In `__init__()` after `self.send_stop_event`:

```python
        self.send_pause_event = threading.Event()
```

- [ ] **Step 7: Run controller tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_controllers.py -q
```

Expected: all controller tests pass.

- [ ] **Step 8: Commit Task 5**

```bash
git add app/constants.py app/controllers/state_controller.py app/controllers/workspace_controller.py app/ui/builders.py main.py tests/test_controllers.py
git commit -m "Add sending governance controls"
```

---

### Task 6: Documentation and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `MAINTENANCE.md`

- [ ] **Step 1: Document user-visible governance behavior**

Modify `README.md` under `What It Does` by adding:

```markdown
- Applies send-governance checks before SMTP delivery: suppression list, duplicate policy, and per-account send limits.
- Supports pausing and resuming batch tasks without re-sending completed rows.
```

- [ ] **Step 2: Update maintenance queue**

Modify `MAINTENANCE.md` `Known Follow-Up Queue` by replacing:

```markdown
- add suppression-list support before positioning the app as a production outreach sender
```

with:

```markdown
- validate suppression-list and pause/resume behavior with a real desktop install before public binary distribution
```

- [ ] **Step 3: Run full verification**

Run:

```bash
.venv/bin/python -m compileall -q app license-platform/apps/api/app main.py
.venv/bin/python -m pytest -q -rs
git diff --check
git ls-files | rg '(^|/)(\.venv|__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|build|dist|node_modules|\.DS_Store)(/|$)|\.pyc$|\.sqlite3?$|\.db$|\.egg-info'
rg -n '(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|password\s*=\s*['"'"'"][^'"'"'"]+|api[_-]?key\s*=\s*['"'"'"][^'"'"'"]+|secret\s*=\s*['"'"'"][^'"'"'"]+)' app license-platform tests README.md docs .github requirements.txt requirements-dev.txt LICENSE NOTICE
```

Expected:

- compileall exits 0
- pytest exits 0 with no skipped tests caused by project code
- `git diff --check` exits 0
- tracked generated-file scan prints no output
- secret scan prints no real secrets

- [ ] **Step 4: Commit Task 6**

```bash
git add README.md MAINTENANCE.md
git commit -m "Document sending governance behavior"
```

---

## Final Review Checklist

- [ ] Suppression entries can be added, imported, exported, queried, and removed.
- [ ] Account usage is persisted only after successful SMTP send.
- [ ] Quota checks block before SMTP delivery.
- [ ] Policy service returns explicit statuses for invalid, suppressed, duplicate, rate-limited, and sendable rows.
- [ ] Batch resume skips rows already recorded for the same task.
- [ ] Pause marks task `paused`; stop remains terminal.
- [ ] Existing duplicate-policy tests still pass.
- [ ] Full verification commands pass.
