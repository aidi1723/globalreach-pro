from __future__ import annotations

from datetime import datetime, timezone

from app.db import connect, init_db


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_admin_user_by_email(email: str):
    init_db()
    normalized_email = normalize_email(email)
    with connect() as conn:
        return conn.execute(
            """
            SELECT * FROM admin_users
            WHERE email = ?
            LIMIT 1
            """,
            (normalized_email,),
        ).fetchone()


def get_admin_user_by_id(admin_user_id: int):
    init_db()
    with connect() as conn:
        return conn.execute(
            """
            SELECT * FROM admin_users
            WHERE id = ?
            LIMIT 1
            """,
            (admin_user_id,),
        ).fetchone()


def create_or_update_admin_user(email: str, password_hash: str, role: str = "admin", status: str = "active") -> int:
    init_db()
    normalized_email = normalize_email(email)
    now = utc_now()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id FROM admin_users
            WHERE email = ?
            LIMIT 1
            """,
            (normalized_email,),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE admin_users
                SET password_hash = ?, role = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (password_hash, role.strip() or "admin", status.strip() or "active", now, row["id"]),
            )
            return int(row["id"])
        conn.execute(
            """
            INSERT INTO admin_users(email, password_hash, role, status, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (normalized_email, password_hash, role.strip() or "admin", status.strip() or "active", now, now),
        )
        return int(
            conn.execute(
                """
                SELECT id FROM admin_users
                WHERE email = ?
                LIMIT 1
                """,
                (normalized_email,),
            ).fetchone()["id"]
        )
