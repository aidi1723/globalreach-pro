from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote

from app.services.secret_store import SecretStore, create_default_secret_store


SENSITIVE_STATE_KEYS = {
    "ai_api_key",
    "license_key",
    "license_activation_token",
}

SECRET_REF_PREFIX = "secret://globalreach-pro/"


def _canonical_quota_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.replace(tzinfo=None).isoformat(timespec="seconds")


class AppStorage:
    def __init__(self, db_path: Path, secret_store: SecretStore | None = None):
        self.db_path = Path(db_path)
        self.secret_store = secret_store or create_default_secret_store()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS smtp_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT UNIQUE NOT NULL,
                    provider TEXT NOT NULL,
                    sender_email TEXT NOT NULL,
                    sender_name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    security TEXT NOT NULL,
                    dkim_selector TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS send_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_count INTEGER NOT NULL,
                    dataset_fingerprint TEXT NOT NULL DEFAULT '',
                    success_count INTEGER NOT NULL,
                    failure_count INTEGER NOT NULL,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    review_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS send_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    row_index INTEGER NOT NULL,
                    recipient_email TEXT NOT NULL,
                    account_label TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES send_tasks(id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_send_results_task_id
                ON send_results(task_id, id DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_send_results_recipient_status
                ON send_results(recipient_email COLLATE NOCASE, status)
                """
            )
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
            self._backfill_account_send_usage(conn)
            self._ensure_column(conn, "send_tasks", "skipped_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "send_tasks", "review_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "send_tasks", "dataset_fingerprint", "TEXT NOT NULL DEFAULT ''")
            self._migrate_plaintext_secrets(conn)

    def _ensure_column(self, conn, table_name: str, column_name: str, definition: str):
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        if any(str(row[1]).lower() == column_name.lower() for row in rows):
            return
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _backfill_account_send_usage(self, conn):
        rows = conn.execute(
            """
            SELECT account_label, recipient_email, task_id, sent_at
            FROM send_results
            WHERE status = 'sent'
            """
        ).fetchall()
        for account_label, recipient_email, task_id, sent_at in rows:
            try:
                canonical_sent_at = _canonical_quota_timestamp(str(sent_at))
            except (TypeError, ValueError):
                continue
            conn.execute(
                """
                INSERT INTO account_send_usage(account_label, recipient_email, task_id, sent_at)
                SELECT ?, ?, ?, ?
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM account_send_usage
                    WHERE account_label = ?
                      AND recipient_email = ? COLLATE NOCASE
                      AND task_id = ?
                      AND sent_at = ?
                )
                """,
                (
                    account_label,
                    recipient_email,
                    task_id,
                    canonical_sent_at,
                    account_label,
                    recipient_email,
                    task_id,
                    canonical_sent_at,
                ),
            )

    def _secret_ref(self, key: str) -> str:
        return SECRET_REF_PREFIX + quote(key, safe="")

    def _secret_key_from_ref(self, value: str) -> str:
        if not value.startswith(SECRET_REF_PREFIX):
            return ""
        return unquote(value[len(SECRET_REF_PREFIX) :])

    def _store_secret_value(self, key: str, value: str) -> str:
        if not value:
            self.secret_store.delete(key)
            return ""
        self.secret_store.set(key, value)
        return self._secret_ref(key)

    def _resolve_secret_value(self, stored_value: str) -> str:
        key = self._secret_key_from_ref(stored_value)
        if not key:
            return stored_value
        return self.secret_store.get(key)

    def _migrate_plaintext_secrets(self, conn):
        smtp_rows = conn.execute("SELECT label, password FROM smtp_accounts").fetchall()
        for label, password in smtp_rows:
            raw_password = str(password or "")
            if not raw_password or raw_password.startswith(SECRET_REF_PREFIX):
                continue
            secret_key = f"smtp:{label}:password"
            conn.execute(
                "UPDATE smtp_accounts SET password = ? WHERE label = ?",
                (self._store_secret_value(secret_key, raw_password), label),
            )

        placeholders = ",".join("?" for _ in SENSITIVE_STATE_KEYS)
        state_rows = conn.execute(
            f"SELECT key, value FROM app_state WHERE key IN ({placeholders})",
            tuple(SENSITIVE_STATE_KEYS),
        ).fetchall()
        for key, value in state_rows:
            raw_value = str(value or "")
            if not raw_value or raw_value.startswith(SECRET_REF_PREFIX):
                continue
            conn.execute(
                "UPDATE app_state SET value = ? WHERE key = ?",
                (self._store_secret_value(f"state:{key}", raw_value), key),
            )

    def log_event(self, level: str, message: str):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events(level, message, created_at) VALUES(?, ?, ?)",
                (level, message, datetime.now().strftime("%H:%M:%S")),
            )

    def list_recent_events(self, limit: int = 10) -> list[tuple[str, str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT created_at, level, message
                FROM events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return list(reversed(rows))

    def set_state(self, key: str, value: str):
        stored_value = (
            self._store_secret_value(f"state:{key}", value)
            if key in SENSITIVE_STATE_KEYS
            else value
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_state(key, value, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, stored_value, datetime.now().isoformat(timespec="seconds")),
            )

    def get_state(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_state WHERE key = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        return self._resolve_secret_value(str(row[0]))

    def save_smtp_account(self, account: dict[str, str | int]):
        now = datetime.now().isoformat(timespec="seconds")
        label = str(account["label"])
        password_ref = self._store_secret_value(
            f"smtp:{label}:password",
            str(account.get("password", "")),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO smtp_accounts(
                    label, provider, sender_email, sender_name, username, password,
                    host, port, security, dkim_selector, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(label) DO UPDATE SET
                    provider = excluded.provider,
                    sender_email = excluded.sender_email,
                    sender_name = excluded.sender_name,
                    username = excluded.username,
                    password = excluded.password,
                    host = excluded.host,
                    port = excluded.port,
                    security = excluded.security,
                    dkim_selector = excluded.dkim_selector,
                    updated_at = excluded.updated_at
                """,
                (
                    label,
                    account["provider"],
                    account["sender_email"],
                    account["sender_name"],
                    account["username"],
                    password_ref,
                    account["host"],
                    int(account["port"]),
                    account["security"],
                    account["dkim_selector"],
                    now,
                    now,
                ),
            )

    def list_smtp_accounts(self) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT label, provider, sender_email, sender_name, username, password,
                       host, port, security, dkim_selector
                FROM smtp_accounts
                ORDER BY label COLLATE NOCASE ASC
                """
            ).fetchall()
        return [
            {
                "label": row[0],
                "provider": row[1],
                "sender_email": row[2],
                "sender_name": row[3],
                "username": row[4],
                "password": self._resolve_secret_value(str(row[5])),
                "host": row[6],
                "port": str(row[7]),
                "security": row[8],
                "dkim_selector": row[9],
            }
            for row in rows
        ]

    def get_smtp_account(self, label: str) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT label, provider, sender_email, sender_name, username, password,
                       host, port, security, dkim_selector
                FROM smtp_accounts
                WHERE label = ?
                """,
                (label,),
            ).fetchone()
        if not row:
            return None
        return {
            "label": row[0],
            "provider": row[1],
            "sender_email": row[2],
            "sender_name": row[3],
            "username": row[4],
            "password": self._resolve_secret_value(str(row[5])),
            "host": row[6],
            "port": str(row[7]),
            "security": row[8],
            "dkim_selector": row[9],
        }

    def delete_smtp_account(self, label: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM smtp_accounts WHERE label = ?", (label,))
        self.secret_store.delete(f"smtp:{label}:password")

    def create_send_task(
        self,
        label: str,
        source_file: str,
        total_count: int,
        dataset_fingerprint: str = "",
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO send_tasks(
                    label, source_file, status, total_count, dataset_fingerprint,
                    success_count, failure_count, skipped_count, review_count,
                    created_at, started_at, finished_at
                )
                VALUES(?, ?, 'pending', ?, ?, 0, 0, 0, 0, ?, '', '')
                """,
                (label, source_file, total_count, dataset_fingerprint, now),
            )
            return int(cursor.lastrowid)

    def update_send_task(
        self,
        task_id: int,
        status: str,
        success_count: int,
        failure_count: int,
        skipped_count: int | None = None,
        review_count: int | None = None,
        started_at: str = "",
        finished_at: str = "",
    ):
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE send_tasks
                SET status = ?,
                    success_count = ?,
                    failure_count = ?,
                    skipped_count = CASE WHEN ? IS NOT NULL THEN ? ELSE skipped_count END,
                    review_count = CASE WHEN ? IS NOT NULL THEN ? ELSE review_count END,
                    started_at = CASE WHEN ? != '' THEN ? ELSE started_at END,
                    finished_at = CASE WHEN ? != '' THEN ? ELSE finished_at END
                WHERE id = ?
                """,
                (
                    status,
                    success_count,
                    failure_count,
                    skipped_count,
                    skipped_count,
                    review_count,
                    review_count,
                    started_at,
                    started_at,
                    finished_at,
                    finished_at,
                    task_id,
                ),
            )

    def add_send_result(
        self,
        task_id: int,
        row_index: int,
        recipient_email: str,
        account_label: str,
        subject: str,
        body: str,
        status: str,
        error_message: str = "",
        sent_at: str | None = None,
    ):
        timestamp = sent_at or datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO send_results(
                    task_id, row_index, recipient_email, account_label, subject, body,
                    status, error_message, sent_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    row_index,
                    recipient_email,
                    account_label,
                    subject,
                    body,
                    status,
                    error_message,
                    timestamp,
                ),
            )

    def list_send_results(self, task_id: int, limit: int = 20) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT row_index, recipient_email, account_label, subject, status, error_message, sent_at
                FROM send_results
                WHERE task_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (task_id, limit),
            ).fetchall()
        return [
            {
                "row_index": str(row[0]),
                "recipient_email": row[1],
                "account_label": row[2],
                "subject": row[3],
                "status": row[4],
                "error_message": row[5],
                "sent_at": row[6],
            }
            for row in rows
        ]

    def get_send_task(self, task_id: int) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, label, source_file, status, total_count, dataset_fingerprint,
                       success_count, failure_count,
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
            "dataset_fingerprint": row[5],
            "success_count": str(row[6]),
            "failure_count": str(row[7]),
            "skipped_count": str(row[8]),
            "review_count": str(row[9]),
            "created_at": row[10],
            "started_at": row[11],
            "finished_at": row[12],
        }

    def list_recorded_row_indexes(self, task_id: int) -> set[int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT row_index
                FROM send_results
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchall()
        return {int(row[0]) for row in rows}

    def summarize_task_results(self, task_id: int) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*)
                FROM send_results
                WHERE task_id = ?
                GROUP BY status
                """,
                (task_id,),
            ).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def latest_send_task(self) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, label, source_file, status, total_count, dataset_fingerprint,
                       success_count, failure_count,
                       skipped_count, review_count, created_at, started_at, finished_at
                FROM send_tasks
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "label": row[1],
            "source_file": row[2],
            "status": row[3],
            "total_count": str(row[4]),
            "dataset_fingerprint": row[5],
            "success_count": str(row[6]),
            "failure_count": str(row[7]),
            "skipped_count": str(row[8]),
            "review_count": str(row[9]),
            "created_at": row[10],
            "started_at": row[11],
            "finished_at": row[12],
        }

    def recipient_send_history(self, recipient_email: str, limit: int = 10) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT r.row_index, r.recipient_email, r.account_label, r.subject, r.status, r.error_message,
                       r.sent_at, t.label
                FROM send_results r
                JOIN send_tasks t ON t.id = r.task_id
                WHERE r.recipient_email = ? COLLATE NOCASE
                ORDER BY r.id DESC
                LIMIT ?
                """,
                (recipient_email.strip(), limit),
            ).fetchall()
        return [
            {
                "row_index": str(row[0]),
                "recipient_email": row[1],
                "account_label": row[2],
                "subject": row[3],
                "status": row[4],
                "error_message": row[5],
                "sent_at": row[6],
                "task_label": row[7],
            }
            for row in rows
        ]

    def count_prior_sent(self, recipient_email: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM send_results
                WHERE recipient_email = ? COLLATE NOCASE
                  AND status = 'sent'
                """,
                (recipient_email.strip(),),
            ).fetchone()
        return int(row[0]) if row else 0

    def list_prior_sent_counts(self, recipient_emails: list[str]) -> dict[str, int]:
        normalized_recipients = sorted(
            {email.strip().lower() for email in recipient_emails if str(email).strip()}
        )
        if not normalized_recipients:
            return {}

        placeholders = ",".join("?" for _ in normalized_recipients)
        query = f"""
            SELECT lower(recipient_email) AS normalized_email, COUNT(*)
            FROM send_results
            WHERE status = 'sent'
              AND recipient_email COLLATE NOCASE IN ({placeholders})
            GROUP BY lower(recipient_email)
        """
        with self._connect() as conn:
            rows = conn.execute(query, tuple(normalized_recipients)).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def add_account_send_usage(
        self,
        account_label: str,
        recipient_email: str,
        task_id: int,
        sent_at: str,
    ):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO account_send_usage(account_label, recipient_email, task_id, sent_at)
                VALUES(?, ?, ?, ?)
                """,
                (
                    account_label,
                    recipient_email.strip().lower(),
                    task_id,
                    _canonical_quota_timestamp(sent_at),
                ),
            )

    def count_account_usage_between(
        self,
        account_label: str,
        window_start: str,
        window_end: str,
    ) -> int:
        canonical_start = _canonical_quota_timestamp(window_start)
        canonical_end = _canonical_quota_timestamp(window_end)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM account_send_usage
                WHERE account_label = ?
                  AND sent_at >= ?
                  AND sent_at <= ?
                """,
                (account_label, canonical_start, canonical_end),
            ).fetchone()
        return int(row[0]) if row else 0

    def upsert_suppression_entry(
        self,
        recipient_email: str,
        reason: str,
        source: str,
    ) -> dict[str, str]:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO suppression_entries(
                    recipient_email, reason, source, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(recipient_email) DO UPDATE SET
                    reason = excluded.reason,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (recipient_email.strip(), reason, source, now, now),
            )
        entry = self.get_suppression_entry(recipient_email)
        if entry is None:
            raise RuntimeError("Suppression entry was not saved.")
        return entry

    def delete_suppression_entry(self, recipient_email: str):
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM suppression_entries WHERE recipient_email = ? COLLATE NOCASE",
                (recipient_email.strip(),),
            )

    def get_suppression_entry(self, recipient_email: str) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT recipient_email, reason, source, created_at
                FROM suppression_entries
                WHERE recipient_email = ? COLLATE NOCASE
                """,
                (recipient_email.strip(),),
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
