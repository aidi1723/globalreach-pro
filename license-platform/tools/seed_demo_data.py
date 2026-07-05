from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.license_manager import manager


def main():
    result = manager.create_license(
        product_code="globalreach_pro",
        customer_name="",
        customer_email="",
        plan_name="标准版",
        max_activations=1,
        expires_at="",
        notes="开发环境演示激活码",
    )
    print(f"created demo license: {result['license_key']}")


if __name__ == "__main__":
    main()
