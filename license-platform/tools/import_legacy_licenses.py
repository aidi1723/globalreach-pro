from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.license_manager import manager
from app.services.products import create_or_update_product


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import legacy licenses into the unified license platform.")
    parser.add_argument("--file", required=True, help="Path to CSV or JSON file")
    parser.add_argument("--product-code", required=True, help="Target product code")
    parser.add_argument("--product-name", default="", help="Optional product name")
    parser.add_argument("--default-plan", default="标准版", help="Default plan name")
    parser.add_argument("--default-max-activations", type=int, default=1, help="Default activation limit")
    parser.add_argument("--operator-id", type=int, default=0, help="Optional operator id for audit logs")
    return parser.parse_args()


def load_rows(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise SystemExit("JSON import file must contain a list of objects.")
        return [dict(item) for item in payload]
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    raise SystemExit("Only .csv and .json import files are supported.")


def pick(row: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def main():
    args = parse_args()
    source_path = Path(args.file).expanduser().resolve()
    rows = load_rows(source_path)

    product = create_or_update_product(args.product_code, args.product_name or args.product_code)
    print(f"product_code={product['product_code']}")
    print(f"rows={len(rows)}")

    imported = 0
    skipped = 0
    for index, row in enumerate(rows, start=1):
        license_key = pick(row, "license_key", "LicenseKey", "key")
        customer_email = pick(row, "customer_email", "email", "CustomerEmail")
        if not license_key or not customer_email:
            skipped += 1
            print(f"skip_row={index} reason=missing_license_key_or_email")
            continue

        customer_name = pick(row, "customer_name", "name", "CustomerName", default=customer_email)
        status = pick(row, "status", "license_status", default="active")
        plan_name = pick(row, "plan_name", "plan", default=args.default_plan)
        expires_at = pick(row, "expires_at", "expiry", "expires")
        notes = pick(row, "notes", "remark", "source", default="legacy import")
        raw_max = pick(row, "max_activations", "device_limit", default=str(args.default_max_activations))
        try:
            max_activations = max(1, int(raw_max))
        except ValueError:
            max_activations = args.default_max_activations

        manager.import_license(
            product_code=product["product_code"],
            license_key=license_key,
            customer_name=customer_name,
            customer_email=customer_email,
            plan_name=plan_name,
            max_activations=max_activations,
            expires_at=expires_at,
            status=status,
            notes=notes,
            operator_id=args.operator_id or None,
        )
        imported += 1

    print(f"imported={imported}")
    print(f"skipped={skipped}")


if __name__ == "__main__":
    main()
