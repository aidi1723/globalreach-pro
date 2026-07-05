from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.auth import hash_password
from app.services.admin_users import create_or_update_admin_user


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or update an admin user for the license platform.")
    parser.add_argument("--email", required=True, help="Admin email")
    parser.add_argument("--password", required=True, help="Admin password")
    parser.add_argument("--role", default="admin", help="Admin role")
    parser.add_argument("--status", default="active", help="Admin status")
    return parser.parse_args()


def main():
    args = parse_args()
    admin_user_id = create_or_update_admin_user(
        email=args.email,
        password_hash=hash_password(args.password),
        role=args.role,
        status=args.status,
    )
    print(f"admin_user_id={admin_user_id}")
    print(f"email={args.email.strip().lower()}")
    print(f"role={args.role.strip() or 'admin'}")
    print(f"status={args.status.strip() or 'active'}")


if __name__ == "__main__":
    main()
