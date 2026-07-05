from __future__ import annotations

import argparse
import secrets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a secure admin auth secret.")
    parser.add_argument("--length", type=int, default=32, help="Secret byte length before URL-safe encoding")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.length < 16:
        raise SystemExit("--length must be at least 16 for a production auth secret.")
    print(secrets.token_urlsafe(args.length))


if __name__ == "__main__":
    main()
