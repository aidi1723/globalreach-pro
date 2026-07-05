from __future__ import annotations

from datetime import datetime, timezone

from app.db import connect, init_db


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_product_code(product_code: str) -> str:
    return product_code.strip().lower().replace(" ", "_")


def list_products() -> list[dict[str, str]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT product_code, product_name, status, created_at, updated_at
            FROM products
            ORDER BY product_code ASC
            """
        ).fetchall()
    return [row.as_dict() for row in rows]


def list_products_with_stats() -> list[dict[str, str | int]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                p.product_code,
                p.product_name,
                p.status,
                p.created_at,
                p.updated_at,
                COALESCE(stats.license_count, 0) AS license_count
            FROM products p
            LEFT JOIN (
                SELECT product_code, COUNT(1) AS license_count
                FROM license_keys
                GROUP BY product_code
            ) AS stats ON stats.product_code = p.product_code
            ORDER BY p.product_code ASC
            """
        ).fetchall()
    return [row.as_dict() for row in rows]


def create_or_update_product(product_code: str, product_name: str, status: str = "active") -> dict[str, str]:
    init_db()
    normalized_code = normalize_product_code(product_code)
    normalized_name = product_name.strip() or "未命名项目"
    normalized_status = status.strip() or "active"
    now = utc_now()

    with connect() as conn:
        row = conn.execute(
            """
            SELECT product_code FROM products
            WHERE product_code = ?
            LIMIT 1
            """,
            (normalized_code,),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE products
                SET product_name = ?, status = ?, updated_at = ?
                WHERE product_code = ?
                """,
                (normalized_name, normalized_status, now, normalized_code),
            )
        else:
            conn.execute(
                """
                INSERT INTO products(product_code, product_name, status, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (normalized_code, normalized_name, normalized_status, now, now),
            )

    return {
        "product_code": normalized_code,
        "product_name": normalized_name,
        "status": normalized_status,
    }


def delete_product(product_code: str) -> dict[str, str]:
    init_db()
    normalized_code = normalize_product_code(product_code)
    with connect() as conn:
        row = conn.execute(
            """
            SELECT product_code, product_name
            FROM products
            WHERE product_code = ?
            LIMIT 1
            """,
            (normalized_code,),
        ).fetchone()
        if not row:
            raise RuntimeError("项目不存在。")

        license_count_row = conn.execute(
            """
            SELECT COUNT(1) AS license_count
            FROM license_keys
            WHERE product_code = ?
            """,
            (normalized_code,),
        ).fetchone()
        license_count = int(license_count_row["license_count"] or 0) if license_count_row else 0
        if license_count > 0:
            raise RuntimeError("该项目下还有激活码，不能直接删除。请先清理激活码。")

        conn.execute(
            "DELETE FROM products WHERE product_code = ?",
            (normalized_code,),
        )

    return {
        "product_code": normalized_code,
        "product_name": str(row["product_name"]),
        "status": "deleted",
    }
