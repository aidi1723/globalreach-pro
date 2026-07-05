# License Platform Deployment

## Goal

Bring the standalone license platform from local MVP to a stable server deployment that the email tool can call over HTTPS.

This deployment is the official production path for licensing.
Customer-facing local activation is not part of the long-term maintenance plan.

## Minimum Production Requirements

- Python 3.11+
- One long random `LICENSE_PLATFORM_ADMIN_AUTH_SECRET`
- One stable database path or PostgreSQL instance
- Reverse proxy with HTTPS
- Process manager such as `systemd`

## Recommended Environment Variables

```bash
LICENSE_PLATFORM_ENV=production
LICENSE_PLATFORM_HOST=127.0.0.1
LICENSE_PLATFORM_PORT=8787
LICENSE_PLATFORM_ADMIN_AUTH_SECRET=replace-with-long-random-secret
LICENSE_PLATFORM_ADMIN_BEARER_TOKEN_TTL_SECONDS=43200
LICENSE_PLATFORM_RATE_LIMIT_WINDOW_SECONDS=60
LICENSE_PLATFORM_RATE_LIMIT_MAX_REQUESTS=30
LICENSE_PLATFORM_API_PREFIX=/api/v1
LICENSE_PLATFORM_DATABASE_URL=sqlite:////opt/license-platform/data/license_platform.sqlite3
```

Notes:

- For the current MVP, sqlite is acceptable for a single-node deployment.
- PostgreSQL is now supported by runtime configuration and is the recommended production choice.
- When `LICENSE_PLATFORM_ENV` is not `development`, the service now requires `LICENSE_PLATFORM_ADMIN_AUTH_SECRET`.
- Public license endpoints now have a basic in-memory IP rate limit. Tune the window and threshold per deployment.

## Local Package Install

From the repository root:

```bash
./.venv/bin/python -m pip install fastapi uvicorn sqlalchemy 'psycopg[binary]' alembic jinja2
```

Or use a dedicated server venv:

```bash
cd license-platform
python3 -m venv .venv
. .venv/bin/activate
pip install fastapi uvicorn sqlalchemy 'psycopg[binary]' alembic jinja2
```

## Run Database Migrations

From the repository root:

```bash
./.venv/bin/python license-platform/tools/run_migrations.py upgrade head
```

For PostgreSQL:

```bash
env \
  LICENSE_PLATFORM_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/license_platform \
  ./.venv/bin/python license-platform/tools/run_migrations.py upgrade head
```

## Start Command

From the repository root:

```bash
env \
  LICENSE_PLATFORM_ENV=production \
  LICENSE_PLATFORM_ADMIN_AUTH_SECRET=replace-with-long-random-secret \
  ./.venv/bin/python license-platform/tools/run_api.py --host 127.0.0.1 --port 8787
```

## Nginx Reverse Proxy Example

```nginx
server {
    listen 443 ssl http2;
    server_name license.agentcoreos.com;

    location / {
        proxy_pass http://127.0.0.1:8787;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## systemd Service Example

```ini
[Unit]
Description=License Platform API
After=network.target

[Service]
WorkingDirectory=/opt/globalreach
Environment=LICENSE_PLATFORM_ENV=production
Environment=LICENSE_PLATFORM_HOST=127.0.0.1
Environment=LICENSE_PLATFORM_PORT=8787
Environment=LICENSE_PLATFORM_ADMIN_AUTH_SECRET=replace-with-long-random-secret
Environment=LICENSE_PLATFORM_DATABASE_URL=sqlite:////opt/globalreach/license-platform/data/license_platform.sqlite3
ExecStart=/opt/globalreach/.venv/bin/python /opt/globalreach/license-platform/tools/run_api.py
Restart=always
RestartSec=3
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
```

## Client Cutover Steps

1. Deploy the API and verify `/health`.
2. Run `license-platform/tools/run_migrations.py upgrade head`.
3. Create an admin user with `license-platform/tools/create_admin_user.py`.
4. Log in through `/api/v1/admin/auth/login` or `/console/login`.
5. Create one real test license through the admin endpoint.
6. On the email tool side, set:
   - `license_api_base_url=https://license.agentcoreos.com`
   - `license_product_code=globalreach_pro`
7. Run one activation on a test machine.
8. Restart the email tool and confirm it hits `validate` instead of asking to reactivate.

## Legacy System Migration

If you already have an older plugin or desktop authorization system, migrate its historical license list first:

```bash
./.venv/bin/python license-platform/tools/import_legacy_licenses.py \
  --file /path/to/legacy-licenses.csv \
  --product-code plugin_system \
  --product-name "Plugin System" \
  --operator-id 1
```

Then verify the imported data in the admin console at `/console`.

## Smoke Test

From the repository root:

```bash
./.venv/bin/python tools/license_server_e2e.py \
  --base-url https://license.agentcoreos.com \
  --product-code globalreach_pro \
  --admin-email admin@example.com \
  --admin-password change-me-now
```

## Current Known Gaps

- No full admin web console yet
- No offline grace-period policy in the client yet
- No SQLAlchemy model metadata or autogenerate workflow yet
