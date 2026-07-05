from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError

from app.db import connect, database_driver, init_db
from app.services.license_keys import generate_license_key


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class LicenseResult:
    ok: bool
    message: str
    code: str = ""
    license_status: str = ""
    activation_status: str = ""
    activation_token: str = ""
    expires_at: str = ""
    plan_name: str = ""
    max_activations: int = 0


class LicenseManager:
    def __init__(self):
        self._lock = threading.Lock()
        init_db()

    def create_license(
        self,
        product_code: str,
        plan_name: str = "标准版",
        max_activations: int = 1,
        customer_name: str = "",
        customer_email: str = "",
        expires_at: str = "",
        validity_seconds: int = 0,
        notes: str = "",
        operator_id: int | None = None,
    ) -> dict[str, str | int | bool]:
        now = utc_now()
        normalized_product = product_code.strip().lower()
        if not normalized_product:
            raise RuntimeError("请先选择项目，再生成激活码。")
        normalized_name, normalized_email = self._normalize_customer_identity(
            customer_name,
            customer_email,
            normalized_product,
        )
        normalized_expiry = self._normalize_expires_at(expires_at)
        normalized_validity_seconds = self._normalize_validity_seconds(validity_seconds, normalized_expiry)
        prefix = normalized_product.upper().replace("-", "_")[:8] or "LIC"
        with self._lock, connect() as conn:
            self._ensure_product(conn, normalized_product)
            customer_id = self._upsert_customer(conn, normalized_name, normalized_email, notes)
            for _ in range(5):
                license_key = generate_license_key(prefix)
                try:
                    conn.execute(
                        """
                        INSERT INTO license_keys(
                            product_code, customer_id, license_key, plan_name, status,
                            max_activations, validity_seconds, expires_at, issued_at, created_at, updated_at, notes
                        )
                        VALUES(?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            normalized_product,
                            customer_id,
                            license_key,
                            plan_name.strip() or "标准版",
                            max_activations,
                            normalized_validity_seconds,
                            normalized_expiry,
                            now,
                            now,
                            now,
                            notes.strip(),
                        ),
                    )
                    self._log_event(
                        conn,
                        int(conn.execute(
                            "SELECT id FROM license_keys WHERE license_key = ?",
                            (license_key,),
                        ).fetchone()["id"]),
                        None,
                        normalized_product,
                        "license_created",
                        {
                            "customer_email": normalized_email,
                            "plan_name": plan_name,
                            "max_activations": max_activations,
                            "validity_seconds": normalized_validity_seconds,
                            "expires_at": normalized_expiry,
                        },
                        operator_id=operator_id,
                    )
                    return {"ok": True, "license_key": license_key}
                except (sqlite3.IntegrityError, SQLAlchemyIntegrityError):
                    continue
        raise RuntimeError("多次尝试后仍未能生成唯一激活码。")

    def import_license(
        self,
        product_code: str,
        license_key: str,
        plan_name: str = "标准版",
        max_activations: int = 1,
        customer_name: str = "",
        customer_email: str = "",
        expires_at: str = "",
        validity_seconds: int = 0,
        status: str = "active",
        notes: str = "",
        operator_id: int | None = None,
    ) -> dict[str, str | int | bool]:
        now = utc_now()
        normalized_product = product_code.strip().lower()
        if not normalized_product:
            raise RuntimeError("请先选择项目，再添加激活码。")
        normalized_name, normalized_email = self._normalize_customer_identity(
            customer_name,
            customer_email,
            normalized_product,
        )
        normalized_expiry = self._normalize_expires_at(expires_at)
        normalized_validity_seconds = self._normalize_validity_seconds(validity_seconds, normalized_expiry)
        normalized_key = license_key.strip().upper()
        normalized_status = status.strip().lower() or "active"

        with self._lock, connect() as conn:
            self._ensure_product(conn, normalized_product)
            customer_id = self._upsert_customer(conn, normalized_name, normalized_email, notes)
            existing = conn.execute(
                "SELECT id FROM license_keys WHERE license_key = ? LIMIT 1",
                (normalized_key,),
            ).fetchone()
            if existing:
                raise RuntimeError(f"激活码已存在：{normalized_key}")
            conn.execute(
                """
                INSERT INTO license_keys(
                    product_code, customer_id, license_key, plan_name, status,
                    max_activations, validity_seconds, expires_at, issued_at, created_at, updated_at, notes
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_product,
                    customer_id,
                    normalized_key,
                    plan_name.strip() or "标准版",
                    normalized_status,
                    max_activations,
                    normalized_validity_seconds,
                    normalized_expiry,
                    now,
                    now,
                    now,
                    notes.strip(),
                ),
            )
            license_key_id = int(
                conn.execute(
                    "SELECT id FROM license_keys WHERE license_key = ?",
                    (normalized_key,),
                ).fetchone()["id"]
            )
            self._log_event(
                conn,
                license_key_id,
                None,
                normalized_product,
                "license_imported",
                {
                    "customer_email": normalized_email,
                    "plan_name": plan_name,
                    "max_activations": max_activations,
                    "validity_seconds": normalized_validity_seconds,
                    "expires_at": normalized_expiry,
                    "status": normalized_status,
                },
                operator_id=operator_id,
            )
        return {"ok": True, "license_key": normalized_key}

    def create_licenses_batch(
        self,
        product_code: str,
        quantity: int,
        plan_name: str,
        max_activations: int,
        expires_at: str = "",
        validity_seconds: int = 0,
        notes: str = "",
        operator_id: int | None = None,
    ) -> dict[str, object]:
        normalized_product = product_code.strip().lower()
        if not normalized_product:
            raise RuntimeError("请先选择项目，再批量生成激活码。")
        if int(quantity) < 1:
            raise RuntimeError("批量生成数量必须大于 0。")
        items: list[str] = []
        normalized_quantity = max(1, min(int(quantity), 500))
        for _ in range(normalized_quantity):
            created = self.create_license(
                product_code=normalized_product,
                customer_name="",
                customer_email="",
                plan_name=plan_name,
                max_activations=max_activations,
                expires_at=expires_at,
                validity_seconds=validity_seconds,
                notes=notes,
                operator_id=operator_id,
            )
            items.append(str(created["license_key"]))
        return {"ok": True, "items": items, "count": len(items)}

    def list_licenses(self, product_code: str = "", license_key: str = "") -> list[dict[str, str | int]]:
        query = """
            SELECT lk.license_key, lk.product_code, lk.plan_name, lk.status, lk.max_activations,
                   lk.validity_seconds, lk.expires_at, lk.last_validated_at, lk.created_at, lk.notes,
                   COALESCE(active_counts.active_activations, 0) AS active_activations,
                   c.name AS customer_name, c.email AS customer_email
            FROM license_keys lk
            LEFT JOIN customers c ON c.id = lk.customer_id
            LEFT JOIN (
                SELECT license_key_id, COUNT(1) AS active_activations
                FROM license_activations
                WHERE status = 'active'
                GROUP BY license_key_id
            ) AS active_counts ON active_counts.license_key_id = lk.id
            WHERE 1 = 1
        """
        params: list[str] = []
        query += " AND lk.status != ?"
        params.append("deleted")
        if product_code.strip():
            query += " AND lk.product_code = ?"
            params.append(product_code.strip().lower())
        if license_key.strip():
            query += " AND lk.license_key = ?"
            params.append(license_key.strip().upper())
        query += " ORDER BY lk.id DESC"
        with connect() as conn:
            rows = conn.execute(query, params).fetchall()
        items: list[dict[str, str | int]] = []
        for row in rows:
            item = row.as_dict()
            item["effective_status"] = self._effective_status(str(item["status"]), str(item["expires_at"] or ""))
            items.append(item)
        return items

    def activate_license(self, payload: dict[str, str]) -> LicenseResult:
        with self._lock, connect() as conn:
            product_code = payload["product_code"].strip().lower()
            license_row = self._load_license(conn, product_code, payload["license_key"])
            if not license_row:
                return self._deny(
                    conn,
                    product_code=product_code,
                    event_type="activation_denied",
                    message="激活码不存在。",
                    code="invalid_license",
                    payload=payload,
                )
            invalid = self._validate_license_row(conn, license_row, payload, "activation_denied")
            if invalid:
                return invalid

            self._lock_license_for_activation(conn, int(license_row["id"]))
            license_row = self._activate_pending_expiry_if_needed(conn, license_row)

            existing = conn.execute(
                """
                SELECT * FROM license_activations
                WHERE license_key_id = ? AND machine_id = ? AND status = 'active'
                ORDER BY id DESC
                LIMIT 1
                """,
                (license_row["id"], payload["machine_id"]),
            ).fetchone()
            if existing:
                self._touch_activation(conn, int(existing["id"]), payload.get("app_version", ""))
                self._touch_license(conn, int(license_row["id"]))
                return self._build_success_result(license_row, existing["activation_token"])

            active_count = conn.execute(
                """
                SELECT COUNT(1) AS count
                FROM license_activations
                WHERE license_key_id = ? AND status = 'active'
                """,
                (license_row["id"],),
            ).fetchone()["count"]
            if int(active_count) >= int(license_row["max_activations"]):
                return self._deny(
                    conn,
                    product_code=str(license_row["product_code"]),
                    event_type="activation_denied",
                    message="该授权已达到设备激活上限，请先释放旧设备。",
                    code="activation_limit_reached",
                    license_status=str(license_row["status"]),
                    license_key_id=int(license_row["id"]),
                    payload=payload,
                )

            now = utc_now()
            token = "act_" + secrets.token_urlsafe(18)
            conn.execute(
                """
                INSERT INTO license_activations(
                    license_key_id, product_code, machine_id, machine_name, device_label,
                    os_name, os_version, app_version, activation_token, status,
                    first_seen_at, last_seen_at, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
                """,
                (
                    license_row["id"],
                    license_row["product_code"],
                    payload["machine_id"],
                    payload.get("machine_name", ""),
                    payload.get("machine_name", ""),
                    payload.get("os_name", ""),
                    payload.get("os_version", ""),
                    payload.get("app_version", ""),
                    token,
                    now,
                    now,
                    now,
                    now,
                ),
            )
            self._touch_license(conn, int(license_row["id"]))
            self._log_event(
                conn,
                int(license_row["id"]),
                int(
                    conn.execute(
                        "SELECT id FROM license_activations WHERE activation_token = ?",
                        (token,),
                    ).fetchone()["id"]
                ),
                str(license_row["product_code"]),
                "activation_created",
                payload,
            )
            return self._build_success_result(license_row, token)

    def validate_license(self, payload: dict[str, str]) -> LicenseResult:
        with self._lock, connect() as conn:
            product_code = payload["product_code"].strip().lower()
            license_row = self._load_license(conn, product_code, payload["license_key"])
            if not license_row:
                return self._deny(
                    conn,
                    product_code=product_code,
                    event_type="validation_denied",
                    message="激活码不存在。",
                    code="invalid_license",
                    payload=payload,
                )
            invalid = self._validate_license_row(conn, license_row, payload, "validation_denied")
            if invalid:
                return invalid

            license_row = self._activate_pending_expiry_if_needed(conn, license_row)

            activation = conn.execute(
                """
                SELECT * FROM license_activations
                WHERE license_key_id = ? AND machine_id = ? AND activation_token = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    license_row["id"],
                    payload["machine_id"],
                    payload.get("activation_token", "").strip(),
                ),
            ).fetchone()
            if not activation:
                return self._deny(
                    conn,
                    product_code=str(license_row["product_code"]),
                    event_type="validation_denied",
                    message="未找到匹配的激活记录。",
                    code="activation_not_found",
                    license_status=str(license_row["status"]),
                    license_key_id=int(license_row["id"]),
                    payload=payload,
                )
            if activation["status"] != "active":
                return self._deny(
                    conn,
                    product_code=str(license_row["product_code"]),
                    event_type="validation_denied",
                    message="当前设备激活已失效。",
                    code="activation_inactive",
                    license_status=str(license_row["status"]),
                    license_key_id=int(license_row["id"]),
                    activation_id=int(activation["id"]),
                    payload=payload,
                )

            self._touch_activation(conn, int(activation["id"]), payload.get("app_version", ""))
            self._touch_license(conn, int(license_row["id"]))
            self._log_event(
                conn,
                int(license_row["id"]),
                int(activation["id"]),
                str(license_row["product_code"]),
                "activation_validated",
                payload,
            )
            return self._build_success_result(license_row, activation["activation_token"])

    def release_license(self, payload: dict[str, str]) -> LicenseResult:
        with self._lock, connect() as conn:
            product_code = payload["product_code"].strip().lower()
            license_row = self._load_license(conn, product_code, payload["license_key"])
            if not license_row:
                return self._deny(
                    conn,
                    product_code=product_code,
                    event_type="release_denied",
                    message="激活码不存在。",
                    code="invalid_license",
                    payload=payload,
                )
            activation = conn.execute(
                """
                SELECT * FROM license_activations
                WHERE license_key_id = ? AND machine_id = ? AND activation_token = ? AND status = 'active'
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    license_row["id"],
                    payload["machine_id"],
                    payload.get("activation_token", "").strip(),
                ),
            ).fetchone()
            if not activation:
                return self._deny(
                    conn,
                    product_code=str(license_row["product_code"]),
                    event_type="release_denied",
                    message="当前机器没有可释放的激活记录。",
                    code="activation_not_found",
                    license_status=str(license_row["status"]),
                    license_key_id=int(license_row["id"]),
                    payload=payload,
                )

            now = utc_now()
            conn.execute(
                """
                UPDATE license_activations
                SET status = 'released', released_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, activation["id"]),
            )
            self._log_event(
                conn,
                int(license_row["id"]),
                int(activation["id"]),
                str(license_row["product_code"]),
                "activation_released",
                payload,
            )
            return LicenseResult(True, "设备激活已释放。", code="", license_status=str(license_row["status"]))

    def disable_license(self, license_key: str, operator_id: int | None = None) -> LicenseResult:
        return self._update_license_status(
            license_key,
            "disabled",
            "license_disabled",
            "激活码已停用。",
            operator_id=operator_id,
        )

    def extend_license(self, license_key: str, expires_at: str, operator_id: int | None = None) -> LicenseResult:
        with self._lock, connect() as conn:
            row = conn.execute(
                "SELECT * FROM license_keys WHERE license_key = ?",
                (license_key.strip().upper(),),
            ).fetchone()
            if not row:
                return LicenseResult(False, "激活码不存在。", code="invalid_license")
            now = utc_now()
            conn.execute(
                "UPDATE license_keys SET validity_seconds = 0, expires_at = ?, updated_at = ? WHERE id = ?",
                (self._normalize_expires_at(expires_at), now, row["id"]),
            )
            self._log_event(
                conn,
                int(row["id"]),
                None,
                str(row["product_code"]),
                "license_extended",
                {"expires_at": self._normalize_expires_at(expires_at)},
                operator_id=operator_id,
            )
            return LicenseResult(
                True,
                "有效期已更新。",
                license_status=str(row["status"]),
                expires_at=self._normalize_expires_at(expires_at),
            )

    def reset_activations(self, license_key: str, operator_id: int | None = None) -> LicenseResult:
        with self._lock, connect() as conn:
            row = conn.execute(
                "SELECT * FROM license_keys WHERE license_key = ?",
                (license_key.strip().upper(),),
            ).fetchone()
            if not row:
                return LicenseResult(False, "激活码不存在。", code="invalid_license")
            now = utc_now()
            conn.execute(
                """
                UPDATE license_activations
                SET status = 'released', released_at = ?, updated_at = ?
                WHERE license_key_id = ? AND status = 'active'
                """,
                (now, now, row["id"]),
            )
            self._log_event(
                conn,
                int(row["id"]),
                None,
                str(row["product_code"]),
                "activation_reset",
                {},
                operator_id=operator_id,
            )
            return LicenseResult(True, "该激活码的设备记录已重置。", license_status=str(row["status"]))

    def delete_license(self, license_key: str, operator_id: int | None = None) -> LicenseResult:
        with self._lock, connect() as conn:
            row = conn.execute(
                "SELECT * FROM license_keys WHERE license_key = ?",
                (license_key.strip().upper(),),
            ).fetchone()
            if not row:
                return LicenseResult(False, "激活码不存在。", code="invalid_license")
            if str(row["status"]).strip().lower() == "deleted":
                return LicenseResult(True, "激活码已删除。", license_status="deleted")

            payload = {"license_key": str(row["license_key"]), "status": str(row["status"])}
            now = utc_now()
            self._log_event(
                conn,
                int(row["id"]),
                None,
                str(row["product_code"]),
                "license_deleted",
                payload,
                operator_id=operator_id,
            )
            conn.execute(
                """
                UPDATE license_activations
                SET status = 'released', released_at = ?, updated_at = ?
                WHERE license_key_id = ? AND status = 'active'
                """,
                (now, now, row["id"]),
            )
            conn.execute(
                "UPDATE license_keys SET status = 'deleted', updated_at = ? WHERE id = ?",
                (now, row["id"]),
            )
            return LicenseResult(True, "激活码已删除。", license_status="deleted")

    def batch_update_licenses(
        self,
        license_keys: list[str],
        action: str,
        expires_at: str = "",
        operator_id: int | None = None,
    ) -> dict[str, object]:
        normalized_keys = self._normalize_license_keys(license_keys)
        if not normalized_keys:
            return {
                "ok": False,
                "action": action,
                "success_count": 0,
                "failed_count": 0,
                "results": [
                    {
                        "license_key": "",
                        "ok": False,
                        "message": "请先提供要处理的激活码。",
                        "code": "empty_license_keys",
                    }
                ],
            }
        if action == "extend" and not expires_at.strip():
            return {
                "ok": False,
                "action": action,
                "success_count": 0,
                "failed_count": len(normalized_keys),
                "results": [
                    {
                        "license_key": "",
                        "ok": False,
                        "message": "批量更新有效期时，必须填写统一有效期。",
                        "code": "missing_expires_at",
                    }
                ],
            }
        results: list[dict[str, str | bool]] = []
        success_count = 0

        for license_key in normalized_keys:
            if action == "disable":
                result = self.disable_license(license_key, operator_id=operator_id)
            elif action == "reset":
                result = self.reset_activations(license_key, operator_id=operator_id)
            elif action == "delete":
                result = self.delete_license(license_key, operator_id=operator_id)
            elif action == "extend":
                result = self.extend_license(license_key, expires_at, operator_id=operator_id)
            else:
                result = LicenseResult(False, "不支持的批量操作。", code="unsupported_action")

            if result.ok:
                success_count += 1
            results.append(
                {
                    "license_key": license_key,
                    "ok": result.ok,
                    "message": result.message,
                    "code": result.code,
                }
            )

        return {
            "ok": success_count == len(normalized_keys),
            "action": action,
            "success_count": success_count,
            "failed_count": len(normalized_keys) - success_count,
            "results": results,
        }

    def export_backup(self, product_code: str = "") -> dict[str, object]:
        normalized_product = product_code.strip().lower()
        with connect() as conn:
            products_query = "SELECT * FROM products"
            products_params: list[str] = []
            if normalized_product:
                products_query += " WHERE product_code = ?"
                products_params.append(normalized_product)
            products_query += " ORDER BY product_code ASC"
            products = [row.as_dict() for row in conn.execute(products_query, products_params).fetchall()]

            license_query = "SELECT * FROM license_keys"
            license_params: list[str] = []
            if normalized_product:
                license_query += " WHERE product_code = ?"
                license_params.append(normalized_product)
            license_query += " ORDER BY id DESC"
            licenses = [row.as_dict() for row in conn.execute(license_query, license_params).fetchall()]

            activation_query = "SELECT * FROM license_activations"
            activation_params: list[str] = []
            if normalized_product:
                activation_query += " WHERE product_code = ?"
                activation_params.append(normalized_product)
            activation_query += " ORDER BY id DESC"
            activations = [row.as_dict() for row in conn.execute(activation_query, activation_params).fetchall()]

            event_query = "SELECT * FROM license_events"
            event_params: list[str] = []
            if normalized_product:
                event_query += " WHERE product_code = ?"
                event_params.append(normalized_product)
            event_query += " ORDER BY id DESC"
            events = [row.as_dict() for row in conn.execute(event_query, event_params).fetchall()]

        return {
            "ok": True,
            "generated_at": utc_now(),
            "product_code": normalized_product,
            "products": products,
            "licenses": licenses,
            "activations": activations,
            "events": events,
        }

    def _update_license_status(
        self,
        license_key: str,
        status: str,
        event_type: str,
        message: str,
        operator_id: int | None = None,
    ) -> LicenseResult:
        with self._lock, connect() as conn:
            row = conn.execute(
                "SELECT * FROM license_keys WHERE license_key = ?",
                (license_key.strip().upper(),),
            ).fetchone()
            if not row:
                return LicenseResult(False, "激活码不存在。", code="invalid_license")
            if str(row["status"]).strip().lower() == "deleted":
                return LicenseResult(False, "该激活码已删除。", code="license_deleted")
            now = utc_now()
            conn.execute(
                "UPDATE license_keys SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, row["id"]),
            )
            self._log_event(
                conn,
                int(row["id"]),
                None,
                str(row["product_code"]),
                event_type,
                {"status": status},
                operator_id=operator_id,
            )
            return LicenseResult(True, message, license_status=status)

    def _load_license(self, conn: sqlite3.Connection, product_code: str, license_key: str):
        return conn.execute(
            """
            SELECT * FROM license_keys
            WHERE product_code = ? AND license_key = ?
            LIMIT 1
            """,
            (product_code.strip().lower(), license_key.strip().upper()),
        ).fetchone()

    def _validate_license_row(
        self,
        conn: sqlite3.Connection,
        row,
        payload: dict[str, str],
        event_type: str,
    ) -> LicenseResult | None:
        status = str(row["status"])
        if status == "deleted":
            return self._deny(
                conn,
                product_code=str(row["product_code"]),
                event_type=event_type,
                message="该授权已删除。",
                code="license_deleted",
                license_status=status,
                license_key_id=int(row["id"]),
                payload=payload,
            )
        if status != "active":
            return self._deny(
                conn,
                product_code=str(row["product_code"]),
                event_type=event_type,
                message="该授权已停用。",
                code="license_disabled",
                license_status=status,
                license_key_id=int(row["id"]),
                payload=payload,
            )
        expires_at = str(row["expires_at"] or "")
        if expires_at and self._is_expired(expires_at):
            return self._deny(
                conn,
                product_code=str(row["product_code"]),
                event_type=event_type,
                message="该授权已过期。",
                code="license_expired",
                license_status="expired",
                license_key_id=int(row["id"]),
                payload=payload,
            )
        return None

    def _is_expired(self, expires_at: str) -> bool:
        return parse_timestamp(expires_at) <= datetime.now(timezone.utc)

    def _normalize_expires_at(self, expires_at: str) -> str:
        normalized = expires_at.strip()
        if not normalized:
            return ""
        return parse_timestamp(normalized).isoformat(timespec="seconds")

    def _normalize_validity_seconds(self, validity_seconds: int, expires_at: str) -> int:
        if expires_at:
            return 0
        normalized_seconds = int(validity_seconds or 0)
        if normalized_seconds < 0:
            raise RuntimeError("有效时长不能小于 0。")
        return normalized_seconds

    def _activate_pending_expiry_if_needed(self, conn: sqlite3.Connection, license_row):
        expires_at = str(license_row["expires_at"] or "").strip()
        validity_seconds = int(license_row["validity_seconds"] or 0)
        if expires_at or validity_seconds <= 0:
            return license_row

        activated_expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=validity_seconds)
        ).isoformat(timespec="seconds")
        now = utc_now()
        conn.execute(
            "UPDATE license_keys SET expires_at = ?, updated_at = ? WHERE id = ?",
            (activated_expires_at, now, license_row["id"]),
        )
        self._log_event(
            conn,
            int(license_row["id"]),
            None,
            str(license_row["product_code"]),
            "license_expiry_started",
            {
                "validity_seconds": validity_seconds,
                "expires_at": activated_expires_at,
            },
        )
        refreshed = conn.execute(
            "SELECT * FROM license_keys WHERE id = ?",
            (license_row["id"],),
        ).fetchone()
        return refreshed or license_row

    def _build_success_result(self, license_row, activation_token: str) -> LicenseResult:
        return LicenseResult(
            ok=True,
            message="激活码有效。",
            license_status=str(license_row["status"]),
            activation_status="active",
            activation_token=activation_token,
            expires_at=str(license_row["expires_at"] or ""),
            plan_name=str(license_row["plan_name"] or ""),
            max_activations=int(license_row["max_activations"] or 0),
        )

    def _touch_license(self, conn: sqlite3.Connection, license_key_id: int):
        now = utc_now()
        conn.execute(
            "UPDATE license_keys SET last_validated_at = ?, updated_at = ? WHERE id = ?",
            (now, now, license_key_id),
        )

    def _touch_activation(self, conn: sqlite3.Connection, activation_id: int, app_version: str):
        now = utc_now()
        conn.execute(
            "UPDATE license_activations SET last_seen_at = ?, app_version = ?, updated_at = ? WHERE id = ?",
            (now, app_version, now, activation_id),
        )

    def _lock_license_for_activation(self, conn: sqlite3.Connection, license_key_id: int):
        driver = database_driver()
        if driver == "postgresql":
            conn.execute(
                "SELECT id FROM license_keys WHERE id = ? FOR UPDATE",
                (license_key_id,),
            )
            return
        conn.execute(
            "UPDATE license_keys SET updated_at = updated_at WHERE id = ?",
            (license_key_id,),
        )

    def _ensure_product(self, conn: sqlite3.Connection, product_code: str):
        row = conn.execute(
            "SELECT id FROM products WHERE product_code = ?",
            (product_code,),
        ).fetchone()
        if row:
            return
        now = utc_now()
        conn.execute(
            """
            INSERT INTO products(product_code, product_name, status, created_at, updated_at)
            VALUES(?, ?, 'active', ?, ?)
            """,
            (product_code, "未命名项目", now, now),
        )

    def _normalize_customer_identity(
        self,
        customer_name: str,
        customer_email: str,
        product_code: str,
    ) -> tuple[str, str]:
        normalized_name = customer_name.strip() or "未登记"
        normalized_email = customer_email.strip().lower()
        if normalized_email:
            return normalized_name, normalized_email
        suffix = secrets.token_hex(8)
        email = f"{product_code or 'license'}.{suffix}@local.invalid"
        return normalized_name, email

    def _normalize_license_keys(self, license_keys: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_key in license_keys:
            candidate = raw_key.strip().upper()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)
        return normalized

    def _effective_status(self, status: str, expires_at: str) -> str:
        normalized_status = status.strip().lower()
        if normalized_status == "disabled":
            return "disabled"
        if expires_at and self._is_expired(expires_at):
            return "expired"
        return "active"

    def _upsert_customer(self, conn: sqlite3.Connection, name: str, email: str, notes: str) -> int:
        row = conn.execute(
            "SELECT id FROM customers WHERE email = ?",
            (email,),
        ).fetchone()
        now = utc_now()
        if row:
            conn.execute(
                "UPDATE customers SET name = ?, notes = ?, updated_at = ? WHERE id = ?",
                (name.strip() or email, notes.strip(), now, row["id"]),
            )
            return int(row["id"])
        conn.execute(
            """
            INSERT INTO customers(name, email, company, notes, created_at, updated_at)
            VALUES(?, ?, '', ?, ?, ?)
            """,
            (name.strip() or email, email, notes.strip(), now, now),
        )
        return int(
            conn.execute(
                "SELECT id FROM customers WHERE email = ?",
                (email,),
            ).fetchone()["id"]
        )

    def _log_event(
        self,
        conn: sqlite3.Connection,
        license_key_id: int | None,
        activation_id: int | None,
        product_code: str,
        event_type: str,
        payload: dict,
        operator_id: int | None = None,
    ):
        conn.execute(
            """
            INSERT INTO license_events(
                license_key_id, activation_id, product_code, event_type, operator_id, payload_json, created_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                license_key_id,
                activation_id,
                product_code,
                event_type,
                operator_id,
                json.dumps(payload, ensure_ascii=False),
                utc_now(),
            ),
        )

    def _deny(
        self,
        conn: sqlite3.Connection,
        product_code: str,
        event_type: str,
        message: str,
        code: str,
        payload: dict[str, str],
        license_status: str = "",
        license_key_id: int | None = None,
        activation_id: int | None = None,
    ) -> LicenseResult:
        denied_payload = dict(payload)
        denied_payload["code"] = code
        denied_payload["message"] = message
        self._log_event(conn, license_key_id, activation_id, product_code, event_type, denied_payload)
        return LicenseResult(False, message, code=code, license_status=license_status)


manager = LicenseManager()
