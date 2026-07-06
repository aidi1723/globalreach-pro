import json
import os
import subprocess
import sys
from pathlib import Path


def test_license_platform_database_driver_supports_postgres_url(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    api_root = project_root / "license-platform" / "apps" / "api"
    db_path = tmp_path / "license_platform.sqlite3"

    code = """
import json
import sys

sys.path.insert(0, sys.argv[1])

from app.db import POSTGRES_SCHEMA_PATH, _load_schema_statements, database_driver
from app.config import settings

payload = {
    "driver": database_driver(),
    "schema_exists": POSTGRES_SCHEMA_PATH.exists(),
    "schema_has_admin_users": any("CREATE TABLE IF NOT EXISTS admin_users" in stmt for stmt in _load_schema_statements()),
}
print(json.dumps(payload))
"""

    sqlite_result = subprocess.run(
        [sys.executable, "-c", code, str(api_root)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "LICENSE_PLATFORM_DATABASE_URL": f"sqlite:///{db_path}"},
    )
    sqlite_payload = json.loads(sqlite_result.stdout.strip())
    assert sqlite_payload["driver"] == "sqlite"

    postgres_result = subprocess.run(
        [sys.executable, "-c", code, str(api_root)],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "LICENSE_PLATFORM_DATABASE_URL": "postgresql+psycopg://postgres:postgres@localhost:5432/license_platform",
        },
    )
    postgres_payload = json.loads(postgres_result.stdout.strip())
    assert postgres_payload["driver"] == "postgresql"
    assert postgres_payload["schema_exists"] is True
    assert postgres_payload["schema_has_admin_users"] is True


def test_license_platform_alembic_upgrade_initializes_sqlite_schema(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "alembic_license_platform.sqlite3"

    result = subprocess.run(
        [
            sys.executable,
            "license-platform/tools/run_migrations.py",
            "upgrade",
            "head",
            "--db-url",
            f"sqlite:///{db_path}",
        ],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    inspect_code = """
import json
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
tables = sorted(
    row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
)
print(json.dumps({"tables": tables}))
"""
    inspect_result = subprocess.run(
        [sys.executable, "-c", inspect_code, str(db_path)],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    payload = json.loads(inspect_result.stdout.strip())
    assert "admin_users" in payload["tables"]
    assert "license_keys" in payload["tables"]
    assert "license_activations" in payload["tables"]
    assert "alembic_version" in payload["tables"]


def test_license_platform_sqlite_schema_rejects_duplicate_active_machine(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    api_root = project_root / "license-platform" / "apps" / "api"
    db_path = tmp_path / "active_machine_unique.sqlite3"

    code = """
import json
import sqlite3
import sys

sys.path.insert(0, sys.argv[1])

from app.db import init_db

init_db()

conn = sqlite3.connect(sys.argv[2])
conn.execute("INSERT INTO products(product_code, product_name, status, created_at, updated_at) VALUES('globalreach', 'GlobalReach', 'active', 'now', 'now')")
conn.execute("INSERT INTO license_keys(product_code, license_key, issued_at, created_at, updated_at) VALUES('globalreach', 'MAIL-AAAA-BBBB', 'now', 'now', 'now')")
license_id = conn.execute("SELECT id FROM license_keys WHERE license_key = 'MAIL-AAAA-BBBB'").fetchone()[0]
conn.execute(
    "INSERT INTO license_activations(license_key_id, product_code, machine_id, activation_token, status, first_seen_at, last_seen_at, created_at, updated_at) VALUES(?, 'globalreach', 'machine-1', 'act_1', 'active', 'now', 'now', 'now', 'now')",
    (license_id,),
)
duplicate_rejected = False
try:
    conn.execute(
        "INSERT INTO license_activations(license_key_id, product_code, machine_id, activation_token, status, first_seen_at, last_seen_at, created_at, updated_at) VALUES(?, 'globalreach', 'machine-1', 'act_2', 'active', 'now', 'now', 'now', 'now')",
        (license_id,),
    )
except sqlite3.IntegrityError:
    duplicate_rejected = True
print(json.dumps({"duplicate_rejected": duplicate_rejected}))
"""

    result = subprocess.run(
        [sys.executable, "-c", code, str(api_root), str(db_path)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "LICENSE_PLATFORM_DATABASE_URL": f"sqlite:///{db_path}"},
    )
    payload = json.loads(result.stdout.strip())
    assert payload["duplicate_rejected"] is True


def test_license_platform_alembic_scaffold_files_exist():
    project_root = Path(__file__).resolve().parents[1]
    expected_files = [
        project_root / "license-platform" / "alembic.ini",
        project_root / "license-platform" / "alembic" / "env.py",
        project_root / "license-platform" / "alembic" / "script.py.mako",
        project_root / "license-platform" / "alembic" / "versions" / "20260414_000001_init_license_platform.py",
        project_root / "license-platform" / "database" / "sqlite_schema.sql",
        project_root / "license-platform" / "tools" / "run_migrations.py",
    ]
    for path in expected_files:
        assert path.exists(), f"missing expected Alembic scaffold file: {path}"
