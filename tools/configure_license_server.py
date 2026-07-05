from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.db import AppStorage


def main():
    parser = argparse.ArgumentParser(description="Configure server-mode licensing for the email tool.")
    parser.add_argument("--api-base-url", default="", help="License API base URL")
    parser.add_argument("--product-code", default="", help="License product code")
    parser.add_argument("--clear", action="store_true", help="Clear stored server-mode license settings")
    args = parser.parse_args()

    storage = AppStorage(PROJECT_ROOT / "app" / "storage" / "globalreach.db")
    if args.clear:
        storage.set_state("license_api_base_url", "")
        storage.set_state("license_product_code", "")
        storage.set_state("license_provider", "local")
        print("cleared server license configuration")
        return

    storage.set_state("license_api_base_url", args.api_base_url.strip())
    storage.set_state("license_product_code", args.product_code.strip())
    storage.set_state("license_provider", "server" if args.api_base_url.strip() and args.product_code.strip() else "local")
    print(f"license_api_base_url={args.api_base_url.strip()}")
    print(f"license_product_code={args.product_code.strip()}")


if __name__ == "__main__":
    main()
