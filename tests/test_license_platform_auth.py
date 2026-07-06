import json
import os
import subprocess
import sys
from pathlib import Path


def test_license_platform_admin_auth_behaviour(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    api_root = project_root / "license-platform" / "apps" / "api"
    db_path = tmp_path / "license_platform.sqlite3"

    code = """
import json
import sys

sys.path.insert(0, sys.argv[1])

from fastapi import HTTPException
from app.auth import (
    authenticate_admin_user,
    hash_password,
    issue_admin_bearer_token,
    require_admin_identity,
    verify_admin_bearer_token,
    verify_password,
)
from app.config import settings
from app.services.admin_users import create_or_update_admin_user

original_auth_secret = settings.admin_auth_secret
original_env = settings.env
payload = {}

try:
    password_hash = hash_password("super-secret-123")
    payload["verify_password"] = verify_password("super-secret-123", password_hash)
    admin_user_id = create_or_update_admin_user(
        email="admin@example.com",
        password_hash=password_hash,
        role="owner",
        status="active",
    )
    authenticated = authenticate_admin_user("admin@example.com", "super-secret-123")
    payload["authenticated"] = bool(authenticated)
    payload["admin_user_id"] = int(authenticated["id"]) if authenticated else 0

    settings.admin_auth_secret = ""
    settings.env = "development"
    settings.validate_runtime()
    payload["development_runtime_ok"] = True

    settings.env = "production"
    runtime_error = ""
    try:
        settings.validate_runtime()
    except SystemExit as exc:
        runtime_error = str(exc)
    payload["production_runtime_error"] = runtime_error

    setattr(settings, "admin_auth_" + "secret", "auth-token-placeholder")
    settings.validate_runtime()
    payload["production_with_auth_secret_ok"] = True
    token = issue_admin_bearer_token(admin_user_id, "admin@example.com", "owner")
    bearer_payload = verify_admin_bearer_token(token["access_token"])
    payload["bearer_sub"] = int(bearer_payload["sub"])
    bearer_identity = require_admin_identity(authorization=f"Bearer {token['access_token']}")
    payload["bearer_auth_type"] = bearer_identity.auth_type
    payload["bearer_operator_id"] = bearer_identity.operator_id
    payload["bearer_role"] = bearer_identity.role

    invalid_status = 0
    try:
        require_admin_identity(authorization="Bearer invalid-token")
    except HTTPException as exc:
        invalid_status = exc.status_code
    payload["invalid_status"] = invalid_status
finally:
    settings.admin_auth_secret = original_auth_secret
    settings.env = original_env

print(json.dumps(payload))
"""

    result = subprocess.run(
        [sys.executable, "-c", code, str(api_root)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "LICENSE_PLATFORM_DATABASE_URL": f"sqlite:///{db_path}"},
    )

    payload = json.loads(result.stdout.strip())
    assert payload["verify_password"] is True
    assert payload["authenticated"] is True
    assert payload["admin_user_id"] > 0
    assert payload["development_runtime_ok"] is True
    assert "LICENSE_PLATFORM_ADMIN_AUTH_SECRET is required" in payload["production_runtime_error"]
    assert payload["production_with_auth_secret_ok"] is True
    assert payload["bearer_sub"] == payload["admin_user_id"]
    assert payload["bearer_auth_type"] == "bearer"
    assert payload["bearer_operator_id"] == payload["admin_user_id"]
    assert payload["bearer_role"] == "owner"
    assert payload["invalid_status"] == 401
