from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException, status

from app.config import settings
from app.services.admin_users import get_admin_user_by_email, get_admin_user_by_id, normalize_email


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _effective_auth_secret() -> str:
    return settings.admin_auth_secret.strip()


def hash_password(password: str, *, salt: str | None = None, iterations: int = 200_000) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    normalized_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        normalized_salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${normalized_salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, raw_iterations, salt, expected_digest = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    derived = hash_password(password, salt=salt, iterations=int(raw_iterations))
    return secrets.compare_digest(derived, password_hash)


def authenticate_admin_user(email: str, password: str):
    user = get_admin_user_by_email(email)
    if not user or str(user["status"]) != "active":
        return None
    if not verify_password(password, str(user["password_hash"])):
        return None
    return user


def _urlsafe_b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def issue_admin_bearer_token(admin_user_id: int, email: str, role: str) -> dict[str, str]:
    secret = _effective_auth_secret()
    if not secret:
        raise ValueError("Admin auth secret is not configured.")
    expires_at = utc_now() + timedelta(seconds=settings.admin_bearer_token_ttl_seconds)
    payload = {
        "sub": int(admin_user_id),
        "email": normalize_email(email),
        "role": role.strip() or "admin",
        "exp": int(expires_at.timestamp()),
    }
    encoded_payload = _urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "access_token": f"{encoded_payload}.{signature}",
        "expires_at": expires_at.isoformat(timespec="seconds"),
    }


def verify_admin_bearer_token(token: str) -> dict:
    secret = _effective_auth_secret()
    if not secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin auth is not configured.")
    try:
        encoded_payload, provided_signature = token.strip().split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token.") from exc
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not secrets.compare_digest(provided_signature, expected_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token.")
    try:
        payload = json.loads(_urlsafe_b64decode(encoded_payload).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token.") from exc
    if int(payload.get("exp", 0) or 0) <= int(utc_now().timestamp()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token expired.")
    return payload


@dataclass
class AdminIdentity:
    operator_id: int | None
    email: str
    role: str
    auth_type: str


def require_admin_identity(
    authorization: str = Header(default=""),
) -> AdminIdentity:
    raw_authorization = authorization if isinstance(authorization, str) else ""
    bearer = raw_authorization.strip()
    if bearer.lower().startswith("bearer "):
        payload = verify_admin_bearer_token(bearer[7:].strip())
        user = get_admin_user_by_id(int(payload["sub"]))
        if not user or str(user["status"]) != "active":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin user is inactive.")
        return AdminIdentity(
            operator_id=int(user["id"]),
            email=str(user["email"]),
            role=str(user["role"]),
            auth_type="bearer",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid admin credentials.",
    )


def try_get_admin_identity(authorization: str = "") -> AdminIdentity | None:
    try:
        return require_admin_identity(authorization=authorization)
    except HTTPException:
        return None
