from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass
from urllib import error, request


class LicenseAPIError(Exception):
    pass


@dataclass
class LicenseServerSettings:
    base_url: str
    product_code: str
    timeout_seconds: int = 10

    @property
    def enabled(self) -> bool:
        return bool(self.base_url.strip() and self.product_code.strip())

    def endpoint(self, path: str) -> str:
        return self.base_url.rstrip("/") + path


@dataclass
class LicenseStatusSnapshot:
    ok: bool
    message: str
    license_status: str = ""
    activation_status: str = ""
    activation_token: str = ""
    expires_at: str = ""
    plan_name: str = ""
    max_activations: int = 0
    code: str = ""


def load_license_server_settings(storage) -> LicenseServerSettings:
    base_url = (
        os.getenv("GLOBALREACH_LICENSE_API_BASE_URL")
        or storage.get_state("license_api_base_url")
        or ""
    )
    product_code = (
        os.getenv("GLOBALREACH_LICENSE_PRODUCT_CODE")
        or storage.get_state("license_product_code")
        or ""
    )
    return LicenseServerSettings(base_url=base_url.strip(), product_code=product_code.strip())


def build_client_metadata(machine_id: str, app_version: str) -> dict[str, str]:
    return {
        "machine_id": machine_id,
        "machine_name": platform.node() or "",
        "os_name": platform.system() or "",
        "os_version": platform.version() or "",
        "app_version": app_version,
    }


def activate_license(
    settings: LicenseServerSettings,
    license_key: str,
    machine_id: str,
    app_version: str,
) -> LicenseStatusSnapshot:
    payload = {
        "product_code": settings.product_code,
        "license_key": license_key.strip(),
        **build_client_metadata(machine_id, app_version),
    }
    data = _post_json(settings.endpoint("/api/v1/licenses/activate"), payload, settings.timeout_seconds)
    return _snapshot_from_response(data)


def validate_license(
    settings: LicenseServerSettings,
    license_key: str,
    activation_token: str,
    machine_id: str,
    app_version: str,
) -> LicenseStatusSnapshot:
    payload = {
        "product_code": settings.product_code,
        "license_key": license_key.strip(),
        "activation_token": activation_token.strip(),
        "machine_id": machine_id,
        "app_version": app_version,
    }
    data = _post_json(settings.endpoint("/api/v1/licenses/validate"), payload, settings.timeout_seconds)
    return _snapshot_from_response(data)


def release_license(
    settings: LicenseServerSettings,
    license_key: str,
    activation_token: str,
    machine_id: str,
) -> LicenseStatusSnapshot:
    payload = {
        "product_code": settings.product_code,
        "license_key": license_key.strip(),
        "activation_token": activation_token.strip(),
        "machine_id": machine_id,
    }
    data = _post_json(settings.endpoint("/api/v1/licenses/release"), payload, settings.timeout_seconds)
    return _snapshot_from_response(data)


def _snapshot_from_response(data: dict) -> LicenseStatusSnapshot:
    return LicenseStatusSnapshot(
        ok=bool(data.get("ok")),
        message=str(data.get("message", "")),
        license_status=str(data.get("license_status", "")),
        activation_status=str(data.get("activation_status", "")),
        activation_token=str(data.get("activation_token", "")),
        expires_at=str(data.get("expires_at", "")),
        plan_name=str(data.get("plan_name", "")),
        max_activations=int(data.get("max_activations", 0) or 0),
        code=str(data.get("code", "")),
    )


def _post_json(url: str, payload: dict, timeout_seconds: int) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw or "{}")
    except error.HTTPError as exc:
        raise LicenseAPIError(f"HTTP {exc.code}") from exc
    except error.URLError as exc:
        raise LicenseAPIError(f"连接授权服务失败：{exc.reason}") from exc
    except Exception as exc:
        raise LicenseAPIError(str(exc)) from exc
