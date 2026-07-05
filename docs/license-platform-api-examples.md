# License Platform API Examples

## Development Run

From the repository root:

```bash
cd license-platform
python3 -m venv .venv
. .venv/bin/activate
pip install -e . || pip install fastapi uvicorn pydantic sqlalchemy psycopg[binary] alembic jinja2
export LICENSE_PLATFORM_ADMIN_AUTH_SECRET=change-me-secret
python tools/run_api.py
```

Run Alembic migrations first if the database is new:

```bash
python tools/run_migrations.py upgrade head
```

Generate a stronger auth secret if needed:

```bash
python tools/generate_admin_token.py
```

Create an admin user for bearer-login mode:

```bash
python tools/create_admin_user.py --email admin@example.com --password 'change-me-now'
```

Import legacy license data into a product:

```bash
python tools/import_legacy_licenses.py --file /path/to/legacy.csv --product-code plugin_system
```

Default local URL:

```text
http://127.0.0.1:8787
```

## Health Check

```bash
curl http://127.0.0.1:8787/health
```

## Create License

```bash
curl -X POST http://127.0.0.1:8787/api/v1/admin/licenses \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer REPLACE_TOKEN' \
  -d '{
    "product_code": "globalreach_pro",
    "customer_name": "Aidi",
    "customer_email": "aidi@example.com",
    "plan_name": "single-device",
    "max_activations": 1,
    "expires_at": "",
    "notes": "manual test"
  }'
```

## Admin Login

```bash
curl -X POST http://127.0.0.1:8787/api/v1/admin/auth/login \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "admin@example.com",
    "password": "change-me-now"
  }'
```

Use the returned `access_token` as:

```bash
-H 'Authorization: Bearer REPLACE_TOKEN'
```

## Activate

```bash
curl -X POST http://127.0.0.1:8787/api/v1/licenses/activate \
  -H 'Content-Type: application/json' \
  -d '{
    "product_code": "globalreach_pro",
    "license_key": "REPLACE_ME",
    "machine_id": "CYFVK1G3PP",
    "machine_name": "Aidi-MacBook",
    "os_name": "macOS",
    "os_version": "15.4",
    "app_version": "2026.04.14"
  }'
```

## Validate

```bash
curl -X POST http://127.0.0.1:8787/api/v1/licenses/validate \
  -H 'Content-Type: application/json' \
  -d '{
    "product_code": "globalreach_pro",
    "license_key": "REPLACE_ME",
    "activation_token": "REPLACE_TOKEN",
    "machine_id": "CYFVK1G3PP",
    "app_version": "2026.04.14"
  }'
```

## Release

```bash
curl -X POST http://127.0.0.1:8787/api/v1/licenses/release \
  -H 'Content-Type: application/json' \
  -d '{
    "product_code": "globalreach_pro",
    "license_key": "REPLACE_ME",
    "activation_token": "REPLACE_TOKEN",
    "machine_id": "CYFVK1G3PP"
  }'
```

## Admin Operations

### List licenses

```bash
curl "http://127.0.0.1:8787/api/v1/admin/licenses?product_code=globalreach_pro" \
  -H 'Authorization: Bearer REPLACE_TOKEN'
```

### Disable license

```bash
curl -X POST http://127.0.0.1:8787/api/v1/admin/licenses/REPLACE_ME/disable \
  -H 'Authorization: Bearer REPLACE_TOKEN'
```

### Extend license

```bash
curl -X POST http://127.0.0.1:8787/api/v1/admin/licenses/REPLACE_ME/extend \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer REPLACE_TOKEN' \
  -d '{"expires_at":"2027-12-31T00:00:00+00:00"}'
```

### Reset all activations

```bash
curl -X POST http://127.0.0.1:8787/api/v1/admin/licenses/REPLACE_ME/reset-activations \
  -H 'Authorization: Bearer REPLACE_TOKEN'
```

## One-Command E2E Check

From the repository root:

```bash
export LICENSE_PLATFORM_ADMIN_EMAIL=admin@example.com
export LICENSE_PLATFORM_ADMIN_PASSWORD=change-me-now
./.venv/bin/python tools/license_server_e2e.py --configure-app
```
