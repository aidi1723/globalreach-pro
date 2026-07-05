from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.license_api_client import load_license_server_settings
from app.services.license_service import generate_license, get_machine_id, inspect_license
from app.storage.db import AppStorage


def main():
    parser = argparse.ArgumentParser(description="Inspect local activation-code state.")
    parser.add_argument("--machine-id", dest="machine_id", default="", help="Override machine id for inspection")
    parser.add_argument("--key", dest="key", default="", help="Validate a provided activation key")
    args = parser.parse_args()

    machine_id = args.machine_id.strip() or get_machine_id()
    expected_key = generate_license(machine_id)
    storage = AppStorage(PROJECT_ROOT / "app" / "storage" / "globalreach.db")
    settings = load_license_server_settings(storage)

    print(f"machine_id={machine_id}")
    print(f"expected_key={expected_key}")
    print(f"server_mode_enabled={settings.enabled}")
    print(f"license_api_base_url={settings.base_url}")
    print(f"license_product_code={settings.product_code}")

    if args.key.strip():
        snapshot = inspect_license(args.key, machine_id=machine_id)
        print(f"provided_key={snapshot['provided_key']}")
        print(f"valid={snapshot['valid']}")
        print(f"reason={snapshot['reason']}")


if __name__ == "__main__":
    main()
