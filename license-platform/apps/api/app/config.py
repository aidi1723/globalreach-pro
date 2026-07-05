from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]
DEFAULT_SQLITE_PATH = BASE_DIR / "data" / "license_platform.sqlite3"


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    app_name: str = os.getenv("LICENSE_PLATFORM_APP_NAME", "License Platform")
    env: str = os.getenv("LICENSE_PLATFORM_ENV", "development")
    api_prefix: str = os.getenv("LICENSE_PLATFORM_API_PREFIX", "/api/v1")
    host: str = os.getenv("LICENSE_PLATFORM_HOST", "127.0.0.1")
    port: int = int(os.getenv("LICENSE_PLATFORM_PORT", "8787"))
    reload: bool = env_flag("LICENSE_PLATFORM_RELOAD", default=False)
    admin_auth_secret: str = os.getenv("LICENSE_PLATFORM_ADMIN_AUTH_SECRET", "")
    admin_bearer_token_ttl_seconds: int = int(os.getenv("LICENSE_PLATFORM_ADMIN_BEARER_TOKEN_TTL_SECONDS", "43200"))
    public_rate_limit_window_seconds: int = int(os.getenv("LICENSE_PLATFORM_RATE_LIMIT_WINDOW_SECONDS", "60"))
    public_rate_limit_max_requests: int = int(os.getenv("LICENSE_PLATFORM_RATE_LIMIT_MAX_REQUESTS", "30"))
    trust_proxy_headers: bool = env_flag("LICENSE_PLATFORM_TRUST_PROXY_HEADERS", default=False)
    trusted_proxy_ips_raw: str = os.getenv("LICENSE_PLATFORM_TRUSTED_PROXY_IPS", "")
    database_url: str = os.getenv(
        "LICENSE_PLATFORM_DATABASE_URL",
        f"sqlite:///{DEFAULT_SQLITE_PATH}",
    )

    @property
    def is_development(self) -> bool:
        return self.env.strip().lower() in {"development", "dev", "local", "test"}

    @property
    def trusted_proxy_ips(self) -> set[str]:
        return {
            item.strip()
            for item in self.trusted_proxy_ips_raw.split(",")
            if item.strip()
        }

    def validate_runtime(self):
        has_auth_secret = bool(self.admin_auth_secret.strip())
        if not self.is_development and not has_auth_secret:
            raise SystemExit(
                "LICENSE_PLATFORM_ADMIN_AUTH_SECRET is required when LICENSE_PLATFORM_ENV is not development."
            )


settings = Settings()
