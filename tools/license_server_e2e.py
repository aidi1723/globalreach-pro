from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib import error, request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.license_api_client import (  # noqa: E402
    LicenseAPIError,
    LicenseServerSettings,
    activate_license,
    release_license,
    validate_license,
)
from app.services.license_service import get_machine_id  # noqa: E402
from app.storage.db import AppStorage  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an end-to-end license server integration check.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787", help="License API base URL")
    parser.add_argument("--product-code", default="globalreach_pro", help="Product code to test")
    parser.add_argument("--license-key", default="", help="Existing license key to use")
    parser.add_argument("--customer-name", default="Demo Customer", help="Customer name used when creating a key")
    parser.add_argument("--customer-email", default="demo@example.com", help="Customer email used when creating a key")
    parser.add_argument("--plan-name", default="single-device", help="Plan name for generated key")
    parser.add_argument("--max-activations", type=int, default=1, help="Activation limit for generated key")
    parser.add_argument("--machine-id", default="", help="Machine id override")
    parser.add_argument("--app-version", default="dev-e2e", help="App version sent to the API")
    parser.add_argument(
        "--admin-email",
        default=os.getenv("LICENSE_PLATFORM_ADMIN_EMAIL", ""),
        help="Admin email for creating a key through the admin login endpoint",
    )
    parser.add_argument(
        "--admin-password",
        default=os.getenv("LICENSE_PLATFORM_ADMIN_PASSWORD", ""),
        help="Admin password for creating a key through the admin login endpoint",
    )
    parser.add_argument(
        "--configure-app",
        action="store_true",
        help="Write server-mode base URL and product code into app/storage/globalreach.db",
    )
    parser.add_argument(
        "--skip-release",
        action="store_true",
        help="Leave the activation active after validation",
    )
    return parser.parse_args()


def post_json(url: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    merged_headers = {"Content-Type": "application/json"}
    if headers:
        merged_headers.update(headers)
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers=merged_headers, method="POST")
    with request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def admin_login(base_url: str, args: argparse.Namespace) -> str:
    if not args.admin_email.strip() or not args.admin_password.strip():
        raise SystemExit("admin login requires --admin-email and --admin-password")
    payload = {
        "email": args.admin_email.strip(),
        "password": args.admin_password,
    }
    try:
        data = post_json(base_url.rstrip("/") + "/api/v1/admin/auth/login", payload)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"admin login failed: HTTP {exc.code} {detail}".strip()) from exc
    except Exception as exc:
        raise SystemExit(f"admin login failed: {exc}") from exc
    token = str(data.get("access_token", "")).strip()
    if not token:
        raise SystemExit(f"admin login failed: {data}")
    return token


def create_license(base_url: str, product_code: str, args: argparse.Namespace) -> str:
    payload = {
        "product_code": product_code,
        "customer_name": args.customer_name,
        "customer_email": args.customer_email,
        "plan_name": args.plan_name,
        "max_activations": args.max_activations,
        "expires_at": "",
        "notes": "e2e integration check",
    }
    access_token = admin_login(base_url, args)
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        data = post_json(base_url.rstrip("/") + "/api/v1/admin/licenses", payload, headers=headers)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"create license failed: HTTP {exc.code} {detail}".strip()) from exc
    except Exception as exc:
        raise SystemExit(f"create license failed: {exc}") from exc

    if not data.get("ok") or not data.get("license_key"):
        raise SystemExit(f"create license failed: {data}")
    return str(data["license_key"])


def configure_app_storage(base_url: str, product_code: str):
    storage = AppStorage(PROJECT_ROOT / "app" / "storage" / "globalreach.db")
    storage.set_state("license_api_base_url", base_url.strip())
    storage.set_state("license_product_code", product_code.strip())
    storage.set_state("license_provider", "server")


def main():
    args = parse_args()
    base_url = args.base_url.strip().rstrip("/")
    product_code = args.product_code.strip()
    machine_id = args.machine_id.strip() or get_machine_id()
    settings = LicenseServerSettings(base_url=base_url, product_code=product_code)

    if args.configure_app:
        configure_app_storage(base_url, product_code)

    license_key = args.license_key.strip().upper() or create_license(base_url, product_code, args)

    try:
        activation = activate_license(settings, license_key, machine_id, args.app_version)
        validation = validate_license(
            settings,
            license_key,
            activation.activation_token,
            machine_id,
            args.app_version,
        )
        release = None
        if not args.skip_release:
            release = release_license(settings, license_key, activation.activation_token, machine_id)
    except LicenseAPIError as exc:
        raise SystemExit(f"client flow failed: {exc}") from exc

    print(
        json.dumps(
            {
                "base_url": base_url,
                "product_code": product_code,
                "machine_id": machine_id,
                "license_key": license_key,
                "configure_app": bool(args.configure_app),
                "activation": activation.__dict__,
                "validation": validation.__dict__,
                "release": release.__dict__ if release else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
