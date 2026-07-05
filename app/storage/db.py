from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


class AppStorage:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
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
                    success_count INTEGER NOT NULL,
                    failure_count INTEGER NOT NULL,
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
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_state(key, value, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, datetime.now().isoformat(timespec="seconds")),
            )

    def get_state(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_state WHERE key = ?",
                (key,),
            ).fetchone()
        return row[0] if row else None

    def save_smtp_account(self, account: dict[str, str | int]):
        now = datetime.now().isoformat(timespec="seconds")
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
                    account["label"],
                    account["provider"],
                    account["sender_email"],
                    account["sender_name"],
                    account["username"],
                    account["password"],
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
                "password": row[5],
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
            "password": row[5],
            "host": row[6],
            "port": str(row[7]),
            "security": row[8],
            "dkim_selector": row[9],
        }

    def delete_smtp_account(self, label: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM smtp_accounts WHERE label = ?", (label,))

    def create_send_task(self, label: str, source_file: str, total_count: int) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO send_tasks(
                    label, source_file, status, total_count, success_count, failure_count,
                    created_at, started_at, finished_at
                )
                VALUES(?, ?, 'pending', ?, 0, 0, ?, '', '')
                """,
                (label, source_file, total_count, now),
            )
            return int(cursor.lastrowid)

    def update_send_task(
        self,
        task_id: int,
        status: str,
        success_count: int,
        failure_count: int,
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
                    started_at = CASE WHEN ? != '' THEN ? ELSE started_at END,
                    finished_at = CASE WHEN ? != '' THEN ? ELSE finished_at END
                WHERE id = ?
                """,
                (
                    status,
                    success_count,
                    failure_count,
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
    ):
        now = datetime.now().isoformat(timespec="seconds")
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
                    now,
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
                SELECT id, label, source_file, status, total_count, success_count, failure_count,
                       created_at, started_at, finished_at
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
            "success_count": str(row[5]),
            "failure_count": str(row[6]),
            "created_at": row[7],
            "started_at": row[8],
            "finished_at": row[9],
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
