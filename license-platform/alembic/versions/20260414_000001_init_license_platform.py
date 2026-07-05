"""Initial license platform schema.

Revision ID: 20260414_000001
Revises:
Create Date: 2026-04-14 13:30:00
"""

from __future__ import annotations

from pathlib import Path

from alembic import op


revision = "20260414_000001"
down_revision = None
branch_labels = None
depends_on = None


ROOT = Path(__file__).resolve().parents[2]
SQLITE_SCHEMA_PATH = ROOT / "database" / "sqlite_schema.sql"
POSTGRES_SCHEMA_PATH = ROOT / "database" / "schema.sql"


def _split_sql_statements(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False

    for char in script:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        if char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            continue
        current.append(char)

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _schema_statements(dialect_name: str) -> list[str]:
    schema_path = SQLITE_SCHEMA_PATH if dialect_name == "sqlite" else POSTGRES_SCHEMA_PATH
    return _split_sql_statements(schema_path.read_text(encoding="utf-8"))


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    for statement in _schema_statements(dialect_name):
        op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    if dialect_name == "sqlite":
        statements = [
            "DROP INDEX IF EXISTS idx_admin_users_email_status",
            "DROP INDEX IF EXISTS idx_license_events_product_code_created_at",
            "DROP INDEX IF EXISTS idx_license_activations_token_lookup",
            "DROP INDEX IF EXISTS idx_license_activations_machine_lookup",
            "DROP INDEX IF EXISTS idx_license_activations_license_key_status",
            "DROP INDEX IF EXISTS idx_license_keys_product_code_license_key",
            "DROP INDEX IF EXISTS idx_license_keys_product_code",
            "DROP TABLE IF EXISTS admin_users",
            "DROP TABLE IF EXISTS license_events",
            "DROP TABLE IF EXISTS license_activations",
            "DROP TABLE IF EXISTS license_keys",
            "DROP TABLE IF EXISTS customers",
            "DROP TABLE IF EXISTS products",
        ]
    else:
        statements = [
            "DROP INDEX IF EXISTS idx_admin_users_email_status",
            "DROP INDEX IF EXISTS idx_license_events_product_code_created_at",
            "DROP INDEX IF EXISTS idx_license_activations_token_lookup",
            "DROP INDEX IF EXISTS idx_license_activations_machine_lookup",
            "DROP INDEX IF EXISTS idx_license_activations_license_key_status",
            "DROP INDEX IF EXISTS idx_license_keys_product_code_license_key",
            "DROP INDEX IF EXISTS idx_license_keys_product_code",
            "DROP TABLE IF EXISTS admin_users",
            "DROP TABLE IF EXISTS license_events",
            "DROP TABLE IF EXISTS license_activations",
            "DROP TABLE IF EXISTS license_keys",
            "DROP TABLE IF EXISTS customers",
            "DROP TABLE IF EXISTS products",
        ]
    for statement in statements:
        op.execute(statement)
