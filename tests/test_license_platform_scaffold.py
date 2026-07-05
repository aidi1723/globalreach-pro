import os
import subprocess
import sys
from pathlib import Path


def test_license_platform_manager_roundtrip(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    api_root = project_root / "license-platform" / "apps" / "api"
    db_path = tmp_path / "license_platform.sqlite3"
    env = os.environ.copy()
    env["LICENSE_PLATFORM_DATABASE_URL"] = f"sqlite:///{db_path}"

    code = """
import json
import sys
from pathlib import Path

api_root = Path(sys.argv[1])
sys.path.insert(0, str(api_root))

from app.db import connect
from app.services.license_manager import manager

created = manager.create_license(
    product_code="globalreach_pro",
    customer_name="Aidi",
    customer_email="aidi@example.com",
    plan_name="single-device",
    max_activations=1,
    expires_at="",
    notes="test",
)
activation = manager.activate_license(
    {
        "product_code": "globalreach_pro",
        "license_key": created["license_key"],
        "machine_id": "MID-001",
        "machine_name": "Test-Mac",
        "os_name": "macOS",
        "os_version": "15.4",
        "app_version": "2026.04.14",
    }
)
validation = manager.validate_license(
    {
        "product_code": "globalreach_pro",
        "license_key": created["license_key"],
        "activation_token": activation.activation_token,
        "machine_id": "MID-001",
        "app_version": "2026.04.14",
    }
)
release = manager.release_license(
    {
        "product_code": "globalreach_pro",
        "license_key": created["license_key"],
        "activation_token": activation.activation_token,
        "machine_id": "MID-001",
    }
)
print(json.dumps(
    {
        "created": created,
        "activation_ok": activation.ok,
        "validation_ok": validation.ok,
        "release_ok": release.ok,
    }
))
"""

    result = subprocess.run(
        [sys.executable, "-c", code, str(api_root)],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    payload = __import__("json").loads(result.stdout.strip())
    assert payload["created"]["ok"] is True
    assert payload["activation_ok"] is True
    assert payload["validation_ok"] is True
    assert payload["release_ok"] is True


def test_license_platform_manager_admin_flows(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    api_root = project_root / "license-platform" / "apps" / "api"
    db_path = tmp_path / "license_platform.sqlite3"
    env = os.environ.copy()
    env["LICENSE_PLATFORM_DATABASE_URL"] = f"sqlite:///{db_path}"

    code = """
import json
import sys
from pathlib import Path

api_root = Path(sys.argv[1])
sys.path.insert(0, str(api_root))

from app.db import connect
from app.services.license_manager import manager

created = manager.create_license(
    product_code="globalreach_pro",
    customer_name="Aidi",
    customer_email="aidi@example.com",
    plan_name="single-device",
    max_activations=1,
    expires_at="",
    notes="test",
    operator_id=101,
)
license_key = created["license_key"]
first = manager.activate_license(
    {
        "product_code": "globalreach_pro",
        "license_key": license_key,
        "machine_id": "MID-001",
        "machine_name": "Test-1",
        "os_name": "macOS",
        "os_version": "15.4",
        "app_version": "2026.04.14",
    }
)
second = manager.activate_license(
    {
        "product_code": "globalreach_pro",
        "license_key": license_key,
        "machine_id": "MID-002",
        "machine_name": "Test-2",
        "os_name": "macOS",
        "os_version": "15.4",
        "app_version": "2026.04.14",
    }
)
disable = manager.disable_license(license_key, operator_id=101)
reset = manager.reset_activations(license_key, operator_id=101)
extend = manager.extend_license(license_key, "2027-12-31T00:00:00+00:00", operator_id=101)
items = manager.list_licenses("globalreach_pro", license_key)
with connect() as conn:
    operator_ids = [row["operator_id"] for row in conn.execute(
        "SELECT operator_id FROM license_events WHERE operator_id IS NOT NULL ORDER BY id ASC"
    ).fetchall()]
print(json.dumps(
    {
        "first_ok": first.ok,
        "second_ok": second.ok,
        "second_code": second.code,
        "disable_ok": disable.ok,
        "disable_status": disable.license_status,
        "reset_ok": reset.ok,
        "extend_ok": extend.ok,
        "items_len": len(items),
        "item_status": items[0]["status"],
        "operator_ids": operator_ids,
    }
))
"""

    result = subprocess.run(
        [sys.executable, "-c", code, str(api_root)],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    payload = __import__("json").loads(result.stdout.strip())
    assert payload["first_ok"] is True
    assert payload["second_ok"] is False
    assert payload["second_code"] == "activation_limit_reached"
    assert payload["disable_ok"] is True
    assert payload["disable_status"] == "disabled"
    assert payload["reset_ok"] is True
    assert payload["extend_ok"] is True
    assert payload["items_len"] == 1
    assert payload["item_status"] == "disabled"
    assert payload["operator_ids"] == [101, 101, 101, 101]


def test_license_platform_expiry_normalization_and_expiration_check(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    api_root = project_root / "license-platform" / "apps" / "api"
    db_path = tmp_path / "license_platform.sqlite3"
    env = os.environ.copy()
    env["LICENSE_PLATFORM_DATABASE_URL"] = f"sqlite:///{db_path}"

    code = """
import json
import sys
from pathlib import Path

api_root = Path(sys.argv[1])
sys.path.insert(0, str(api_root))

from app.schemas import CreateLicenseRequest, LicenseMutationRequest
from app.services.license_manager import manager

create_payload = CreateLicenseRequest(
    product_code="globalreach_pro",
    customer_name="Aidi",
    customer_email="aidi@example.com",
    plan_name="single-device",
    max_activations=1,
    expires_at="2030-01-01T00:00:00Z",
    notes="test",
)
mutation_payload = LicenseMutationRequest(expires_at="2030-02-01T12:30:00Z")
created = manager.create_license(
    product_code="globalreach_pro",
    customer_name="Aidi",
    customer_email="expired@example.com",
    plan_name="single-device",
    max_activations=1,
    expires_at="2000-01-01T00:00:00Z",
    notes="expired test",
)
activation = manager.activate_license(
    {
        "product_code": "globalreach_pro",
        "license_key": created["license_key"],
        "machine_id": "MID-001",
        "machine_name": "Test-Mac",
        "os_name": "macOS",
        "os_version": "15.4",
        "app_version": "2026.04.14",
    }
)
print(json.dumps(
    {
        "create_expires_at": create_payload.expires_at,
        "mutation_expires_at": mutation_payload.expires_at,
        "activation_ok": activation.ok,
        "activation_code": activation.code,
    }
))
"""

    result = subprocess.run(
        [sys.executable, "-c", code, str(api_root)],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    payload = __import__("json").loads(result.stdout.strip())
    assert payload["create_expires_at"] == "2030-01-01T00:00:00+00:00"
    assert payload["mutation_expires_at"] == "2030-02-01T12:30:00+00:00"
    assert payload["activation_ok"] is False
    assert payload["activation_code"] == "license_expired"


def test_license_platform_pending_validity_starts_on_first_activation(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    api_root = project_root / "license-platform" / "apps" / "api"
    db_path = tmp_path / "pending_validity.sqlite3"
    env = os.environ.copy()
    env["LICENSE_PLATFORM_DATABASE_URL"] = f"sqlite:///{db_path}"

    code = """
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

api_root = Path(sys.argv[1])
sys.path.insert(0, str(api_root))

from app.services.license_manager import manager, parse_timestamp

created = manager.create_license(
    product_code="globalreach_pro",
    customer_name="Aidi",
    customer_email="pending@example.com",
    plan_name="周卡",
    max_activations=1,
    validity_seconds=7 * 24 * 60 * 60,
    expires_at="",
    notes="pending validity",
)
before_items = manager.list_licenses("globalreach_pro", created["license_key"])
activation = manager.activate_license(
    {
        "product_code": "globalreach_pro",
        "license_key": created["license_key"],
        "machine_id": "MID-001",
        "machine_name": "Test-Mac",
        "os_name": "macOS",
        "os_version": "15.4",
        "app_version": "2026.04.14",
    }
)
after_items = manager.list_licenses("globalreach_pro", created["license_key"])
delta_days = round((parse_timestamp(activation.expires_at) - datetime.now(timezone.utc)).total_seconds() / 86400)

print(json.dumps({
    "before_expires_at": before_items[0]["expires_at"],
    "before_validity_seconds": before_items[0]["validity_seconds"],
    "activation_ok": activation.ok,
    "activation_has_expiry": bool(activation.expires_at),
    "after_expires_at": after_items[0]["expires_at"],
    "after_validity_seconds": after_items[0]["validity_seconds"],
    "delta_days": delta_days,
}))
"""

    result = subprocess.run(
        [sys.executable, "-c", code, str(api_root)],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    payload = __import__("json").loads(result.stdout.strip())
    assert payload["before_expires_at"] == ""
    assert payload["before_validity_seconds"] == 7 * 24 * 60 * 60
    assert payload["activation_ok"] is True
    assert payload["activation_has_expiry"] is True
    assert payload["after_expires_at"]
    assert payload["after_validity_seconds"] == 7 * 24 * 60 * 60
    assert 6 <= payload["delta_days"] <= 7


def test_license_platform_create_license_retries_duplicate_key(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    api_root = project_root / "license-platform" / "apps" / "api"
    db_path = tmp_path / "license_platform.sqlite3"
    env = os.environ.copy()
    env["LICENSE_PLATFORM_DATABASE_URL"] = f"sqlite:///{db_path}"

    code = """
import json
import sys
from pathlib import Path

api_root = Path(sys.argv[1])
sys.path.insert(0, str(api_root))

import app.services.license_manager as lm
from app.services.license_manager import manager

original = lm.generate_license_key
issued = iter(["GLOBALRE-DUPE-DUPE-DUPE", "GLOBALRE-DUPE-DUPE-DUPE", "GLOBALRE-UNIQ-UNIQ-UNIQ"])

def fake_generate_license_key(prefix):
    return next(issued)

lm.generate_license_key = fake_generate_license_key
try:
    first = manager.create_license(
        product_code="globalreach_pro",
        customer_name="Aidi",
        customer_email="first@example.com",
        plan_name="single-device",
        max_activations=1,
        expires_at="",
        notes="first",
    )
    second = manager.create_license(
        product_code="globalreach_pro",
        customer_name="Aidi",
        customer_email="second@example.com",
        plan_name="single-device",
        max_activations=1,
        expires_at="",
        notes="second",
    )
finally:
    lm.generate_license_key = original

print(json.dumps({"first": first["license_key"], "second": second["license_key"]}))
"""

    result = subprocess.run(
        [sys.executable, "-c", code, str(api_root)],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    payload = __import__("json").loads(result.stdout.strip())
    assert payload["first"] == "GLOBALRE-DUPE-DUPE-DUPE"
    assert payload["second"] == "GLOBALRE-UNIQ-UNIQ-UNIQ"


def test_license_platform_release_requires_matching_activation_token(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    api_root = project_root / "license-platform" / "apps" / "api"
    db_path = tmp_path / "license_platform.sqlite3"
    env = os.environ.copy()
    env["LICENSE_PLATFORM_DATABASE_URL"] = f"sqlite:///{db_path}"

    code = """
import json
import sys
from pathlib import Path

api_root = Path(sys.argv[1])
sys.path.insert(0, str(api_root))

from app.db import connect
from app.services.license_manager import manager

created = manager.create_license(
    product_code="globalreach_pro",
    customer_name="Aidi",
    customer_email="release@example.com",
    plan_name="single-device",
    max_activations=1,
    expires_at="",
    notes="test",
)
activation = manager.activate_license(
    {
        "product_code": "globalreach_pro",
        "license_key": created["license_key"],
        "machine_id": "MID-001",
        "machine_name": "Test-Mac",
        "os_name": "macOS",
        "os_version": "15.4",
        "app_version": "2026.04.14",
        "client_ip": "127.0.0.1",
    }
)
failed_release = manager.release_license(
    {
        "product_code": "globalreach_pro",
        "license_key": created["license_key"],
        "activation_token": "wrong-token",
        "machine_id": "MID-001",
        "client_ip": "127.0.0.1",
    }
)
success_release = manager.release_license(
    {
        "product_code": "globalreach_pro",
        "license_key": created["license_key"],
        "activation_token": activation.activation_token,
        "machine_id": "MID-001",
        "client_ip": "127.0.0.1",
    }
)
with connect() as conn:
    event_types = [row["event_type"] for row in conn.execute(
        "SELECT event_type FROM license_events ORDER BY id ASC"
    ).fetchall()]
print(json.dumps(
    {
        "failed_release_ok": failed_release.ok,
        "failed_release_code": failed_release.code,
        "success_release_ok": success_release.ok,
        "event_types": event_types,
    }
))
"""

    result = subprocess.run(
        [sys.executable, "-c", code, str(api_root)],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    payload = __import__("json").loads(result.stdout.strip())
    assert payload["failed_release_ok"] is False
    assert payload["failed_release_code"] == "activation_not_found"
    assert payload["success_release_ok"] is True
    assert "release_denied" in payload["event_types"]
