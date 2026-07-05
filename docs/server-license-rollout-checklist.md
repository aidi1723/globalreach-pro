# Server License Rollout Checklist

## Purpose

This checklist translates the unified server-side licensing decision into an execution sequence.

Use this document when:

- deploying `license-platform` to a real server
- cutting `globalreach_pro` over to production server licensing
- preparing the future migration of `zhishu_lead_plugin`

Related decision document:

- [`docs/unified-server-license-plan.md`](/Users/aidi/群发工具/docs/unified-server-license-plan.md)

## Phase 0: Release Decision

Before touching production, confirm these rules are accepted:

- server-side licensing is the only formal customer-facing path
- local activation is internal-only
- `license-platform` is the shared platform
- `globalreach_pro` is the first production product code
- `zhishu_lead_plugin` will migrate later

If one of these is still undecided, stop here and resolve it first.

## Phase 1: Server Preparation

### 1. Choose deployment target

Prepare one stable host with:

- Python 3.11+
- reverse proxy with HTTPS
- one persistent database location
- `systemd` or equivalent process manager

### 2. Prepare environment variables

Recommended first production values:

```bash
LICENSE_PLATFORM_ENV=production
LICENSE_PLATFORM_HOST=127.0.0.1
LICENSE_PLATFORM_PORT=8787
LICENSE_PLATFORM_API_PREFIX=/api/v1
LICENSE_PLATFORM_ADMIN_AUTH_SECRET=replace-with-a-long-random-secret
LICENSE_PLATFORM_ADMIN_BEARER_TOKEN_TTL_SECONDS=43200
LICENSE_PLATFORM_RATE_LIMIT_WINDOW_SECONDS=60
LICENSE_PLATFORM_RATE_LIMIT_MAX_REQUESTS=30
LICENSE_PLATFORM_DATABASE_URL=sqlite:////opt/license-platform/data/license_platform.sqlite3
```

Maintenance notes:

- for a single-node first release, sqlite is acceptable
- for long-term multi-tool production, PostgreSQL is preferred
- the admin auth secret must not be omitted in production

### 3. Install runtime dependencies

From the repo root:

```bash
./.venv/bin/python -m pip install fastapi uvicorn sqlalchemy 'psycopg[binary]' alembic jinja2
```

Or in a dedicated server venv:

```bash
cd license-platform
python3 -m venv .venv
. .venv/bin/activate
pip install fastapi uvicorn sqlalchemy 'psycopg[binary]' alembic jinja2
```

### 4. Run migrations

```bash
./.venv/bin/python license-platform/tools/run_migrations.py upgrade head
```

If using PostgreSQL, set `LICENSE_PLATFORM_DATABASE_URL` first.

### 5. Start the API

```bash
env \
  LICENSE_PLATFORM_ENV=production \
  LICENSE_PLATFORM_ADMIN_AUTH_SECRET=replace-with-a-long-random-secret \
  ./.venv/bin/python license-platform/tools/run_api.py --host 127.0.0.1 --port 8787
```

### 6. Add reverse proxy

Minimum nginx requirements:

- HTTPS enabled
- forward `Host`
- forward `X-Real-IP`
- forward `X-Forwarded-For`
- forward `X-Forwarded-Proto`

### 7. Verify health

Check local service:

```bash
curl http://127.0.0.1:8787/health
```

Check public HTTPS endpoint after proxy:

```bash
curl https://license.agentcoreos.com/health
```

Pass condition:

- response `ok` is `true`
- database is reported ready

## Phase 2: Admin Initialization

### 1. Create admin user

```bash
./.venv/bin/python license-platform/tools/create_admin_user.py \
  --email admin@example.com \
  --password 'change-me-now'
```

### 2. Test admin login

```bash
curl -X POST https://license.agentcoreos.com/api/v1/admin/auth/login \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "admin@example.com",
    "password": "change-me-now"
  }'
```

Pass condition:

- returns `access_token`
- token can be used against `/api/v1/admin/health`

### 3. Create product records

First products to register:

- `globalreach_pro`
- `zhishu_lead_plugin`

Example:

```bash
curl -X POST https://license.agentcoreos.com/api/v1/admin/products \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer REPLACE_TOKEN' \
  -d '{
    "product_code": "globalreach_pro",
    "product_name": "GlobalReach PRO",
    "status": "active"
  }'
```

Repeat for:

```json
{
  "product_code": "zhishu_lead_plugin",
  "product_name": "智枢获客插件",
  "status": "active"
}
```

Pass condition:

- both products appear in `GET /api/v1/admin/products`

## Phase 3: License Issuance Rules

### Standard first commercial setup

For `globalreach_pro`, start with simple plans only:

- `single-device`
- `multi-device`

Do not introduce bundle licensing yet.

### First batch issuance rules

For the first production round, each created license should define:

- `product_code`
- `plan_name`
- `max_activations`
- `expires_at`
- `notes`

Example create call:

```bash
curl -X POST https://license.agentcoreos.com/api/v1/admin/licenses \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer REPLACE_TOKEN' \
  -d '{
    "product_code": "globalreach_pro",
    "customer_name": "Demo Customer",
    "customer_email": "demo@example.com",
    "plan_name": "single-device",
    "max_activations": 1,
    "expires_at": "",
    "notes": "first production check"
  }'
```

Pass condition:

- the returned key activates successfully on a real test machine

## Phase 4: Email Tool Cutover

### 1. Point the client at the production server

The production email tool must use:

- `license_api_base_url=https://license.agentcoreos.com`
- `license_product_code=globalreach_pro`

Current configuration sources:

- environment variables
- app storage keys

Relevant code:

- [`app/services/license_api_client.py`](/Users/aidi/群发工具/app/services/license_api_client.py)
- [`main.py`](/Users/aidi/群发工具/main.py)

### 2. Configure local app storage on a test machine

Use the existing helper:

```bash
./.venv/bin/python tools/license_server_e2e.py \
  --base-url https://license.agentcoreos.com \
  --product-code globalreach_pro \
  --admin-email admin@example.com \
  --admin-password 'change-me-now' \
  --configure-app
```

This writes:

- `license_api_base_url`
- `license_product_code`
- `license_provider=server`

into the app storage database.

### 3. Run real activation

On a clean test machine:

1. start the app
2. copy the shown machine id
3. enter a real server-issued license key
4. confirm activation succeeds
5. close and reopen the app
6. confirm it validates and does not ask for reactivation

### 4. Confirm persisted state

After successful activation, the client should have:

- `license_key`
- `license_machine_id`
- `license_activation_token`
- `license_status`
- `license_expires_at`
- `license_verified_at`

Pass condition:

- second startup uses `validate`
- no local-only activation is required

## Phase 5: Support Readiness

Before customer rollout, support must rehearse these operations:

### 1. Find a license

Use admin list endpoint filtered by:

- `product_code`
- `license_key`

### 2. Disable a license

Use:

- `POST /api/v1/admin/licenses/{license_key}/disable`

### 3. Extend expiry

Use:

- `POST /api/v1/admin/licenses/{license_key}/extend`

### 4. Reset activations

Use:

- `POST /api/v1/admin/licenses/{license_key}/reset-activations`

This is the standard support action when:

- a customer changes machine
- activation limit is reached
- old activation data should be cleared

### 5. Export license list

Use:

- `GET /api/v1/admin/licenses/export`

Pass condition:

- support can complete all five operations without touching the database directly

## Phase 6: Customer-Facing Documentation Cleanup

Before public rollout, confirm external-facing docs do not describe local activation as the normal path.

Required outcome:

- customers receive server-issued license keys
- customer docs describe activation against the licensing service
- local machine-code generation is not documented as a public workflow

## Phase 7: Acceptance Criteria

The rollout is considered complete only if all of the following are true:

- `license-platform` is reachable over HTTPS
- admin login works
- `globalreach_pro` exists as an active product
- a production license can be created
- the email tool can activate successfully
- the email tool can validate successfully on restart
- support can reset activations without manual database edits
- customer documentation no longer presents local activation as the default

## Rollback Rules

If production cutover fails, use this rollback order:

1. stop distributing new customer keys from the broken environment
2. keep the API online if existing activations are still validating
3. revert the email tool configuration only for internal test builds if needed
4. do not delete issued production licenses unless data corruption is confirmed
5. document the failure cause before retrying cutover

Important:

- rollback should prefer configuration rollback, not data deletion
- direct database edits are a last resort

## Future Phase: Plugin Migration

This checklist does not migrate the plugin yet, but it defines the target:

- add `zhishu_lead_plugin` as a real production product
- adapt plugin client requests to the same platform
- migrate support operations from the old Node.js service
- retire the old plugin-only license service after migration verification

When that work starts, create a separate plugin migration checklist rather than editing the email-tool steps above into a mixed workflow.
