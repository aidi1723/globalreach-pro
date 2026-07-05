from __future__ import annotations

import hashlib
import os
import platform
import subprocess
from pathlib import Path


SECRET_SALT = "GlobalReach_2026"
LEGACY_LOCAL_LICENSE_ENV = "GLOBALREACH_ENABLE_LEGACY_LOCAL_LICENSE"


class LicenseError(Exception):
    pass


def _extract_darwin_serial(output: str) -> str | None:
    for line in output.splitlines():
        if "IOPlatformSerialNumber" in line:
            parts = line.split('"')
            if len(parts) >= 2:
                return parts[-2].strip() or None
    return None


def _extract_windows_uuid(output: str) -> str | None:
    values = [line.strip() for line in output.splitlines() if line.strip() and "UUID" not in line]
    return values[0] if values else None


def get_machine_id() -> str:
    system = platform.system()

    try:
        if system == "Darwin":
            output = subprocess.check_output(
                ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                text=True,
            )
            serial = _extract_darwin_serial(output)
            if serial:
                return serial
        elif system == "Windows":
            output = subprocess.check_output(
                ["wmic", "csproduct", "get", "uuid"],
                text=True,
                creationflags=0,
            )
            uuid_value = _extract_windows_uuid(output)
            if uuid_value:
                return uuid_value
        else:
            machine_id_path = Path("/etc/machine-id")
            if machine_id_path.exists():
                return machine_id_path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        raise LicenseError(f"提取机器码失败：{exc}") from exc

    fallback = f"{platform.system()}-{platform.node()}-{platform.machine()}"
    if fallback.strip("-"):
        return hashlib.sha256(fallback.encode()).hexdigest().upper()[:16]
    raise LicenseError("无法提取机器码。")


def generate_license(machine_id: str, secret_salt: str = SECRET_SALT) -> str:
    raw_str = f"{machine_id}{secret_salt}"
    return hashlib.md5(raw_str.encode()).hexdigest().upper()[:16]


def legacy_local_license_enabled() -> bool:
    return os.getenv(LEGACY_LOCAL_LICENSE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def verify_license(user_key: str, machine_id: str | None = None) -> bool:
    mid = machine_id or get_machine_id()
    expected_key = generate_license(mid)
    return user_key.strip().upper() == expected_key


def inspect_license(user_key: str, machine_id: str | None = None) -> dict[str, str | bool]:
    mid = machine_id or get_machine_id()
    normalized_key = user_key.strip().upper()
    expected_key = generate_license(mid)
    if not normalized_key:
        reason = "empty_key"
    elif normalized_key == expected_key:
        reason = "valid"
    else:
        reason = "mismatch"
    return {
        "machine_id": mid,
        "provided_key": normalized_key,
        "expected_key": expected_key,
        "valid": normalized_key == expected_key,
        "reason": reason,
    }
