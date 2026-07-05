from __future__ import annotations

import argparse
import os
from pathlib import Path

from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "alembic.ini"
ALEMBIC_DIR = ROOT / "alembic"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Alembic migrations for the license platform.")
    parser.add_argument(
        "action",
        choices=["upgrade", "downgrade", "current", "history"],
        help="Alembic action to run",
    )
    parser.add_argument(
        "revision",
        nargs="?",
        default="head",
        help="Target revision for upgrade/downgrade. Defaults to head.",
    )
    parser.add_argument(
        "--db-url",
        default="",
        help="Override LICENSE_PLATFORM_DATABASE_URL for this command.",
    )
    return parser.parse_args()


def build_config(db_url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    effective_url = db_url.strip() or os.getenv("LICENSE_PLATFORM_DATABASE_URL", "").strip()
    if effective_url:
        cfg.set_main_option("sqlalchemy.url", effective_url)
        os.environ["LICENSE_PLATFORM_DATABASE_URL"] = effective_url
    return cfg


def main():
    args = parse_args()
    cfg = build_config(args.db_url)

    if args.action == "upgrade":
        command.upgrade(cfg, args.revision)
        return
    if args.action == "downgrade":
        command.downgrade(cfg, args.revision)
        return
    if args.action == "current":
        command.current(cfg)
        return
    if args.action == "history":
        command.history(cfg)
        return
    raise SystemExit(f"Unsupported action: {args.action}")


if __name__ == "__main__":
    main()
