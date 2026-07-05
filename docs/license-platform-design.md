# Independent License Platform Design

## Goal

Build one standalone license platform that can serve multiple desktop tools and plugins.
The email tool is the first client, but the design must support future products without reworking the core model.

This platform replaces the current local-only activation logic in the email tool.

## Core Principles

1. License validity is decided by the server, not by client-side hashing.
2. Every product is identified by a stable `product_code`.
3. A single license platform can issue keys for many products.
4. Activation is bound to device fingerprints and can be released or disabled from the admin side.
5. The client caches only enough data to work smoothly and revalidate later.
6. All admin operations must leave audit logs.

## Product Model

Each client product registers a unique code:

- `email_tool`
- `plugin_system`
- `lead_scraper`
- `erp_sync`

The email tool should use one fixed product code, for example:

- `globalreach_pro`

## Recommended Architecture

### Services

1. `license-api`
Purpose:
- Activation
- Validation
- Release
- Admin CRUD

2. `license-admin`
Purpose:
- Product management
- License issuance
- Activation lookup
- Device reset
- Disable / extend / notes

3. `client-sdk`
Purpose:
- Shared client logic for desktop tools
- Request signing
- Token caching
- Offline grace-period handling

### Suggested Deployment

1. Public API domain
- `https://license.your-domain.com/api`

2. Admin domain
- `https://license-admin.your-domain.com`

3. Database
- PostgreSQL recommended

4. Cache
- Redis optional for rate limiting, sessions, and short-lived activation tokens

## Database Design

### `products`

Purpose:
- Define products supported by the license platform

Fields:
- `id`
- `product_code` unique
- `product_name`
- `status`
- `created_at`
- `updated_at`

Example:
- `product_code = globalreach_pro`
- `product_name = GlobalReach PRO`

### `customers`

Purpose:
- Store customer identity separate from license records

Fields:
- `id`
- `name`
- `email`
- `company`
- `notes`
- `created_at`
- `updated_at`

### `license_keys`

Purpose:
- Main commercial authorization record

Fields:
- `id`
- `product_code`
- `customer_id`
- `license_key` unique
- `plan_name`
- `status`
- `max_activations`
- `expires_at`
- `issued_at`
- `last_validated_at`
- `notes`
- `created_at`
- `updated_at`

Recommended `status` values:
- `active`
- `disabled`
- `expired`
- `revoked`
- `draft`

### `license_activations`

Purpose:
- Track per-device activation records

Fields:
- `id`
- `license_key_id`
- `product_code`
- `machine_id`
- `machine_name`
- `device_label`
- `os_name`
- `os_version`
- `app_version`
- `activation_token`
- `status`
- `first_seen_at`
- `last_seen_at`
- `released_at`
- `created_at`
- `updated_at`

Recommended `status` values:
- `active`
- `released`
- `blocked`

### `license_events`

Purpose:
- Full audit/event history for support and billing disputes

Fields:
- `id`
- `license_key_id`
- `activation_id`
- `product_code`
- `event_type`
- `operator_id`
- `payload_json`
- `created_at`

Recommended `event_type` values:
- `license_created`
- `license_disabled`
- `license_extended`
- `activation_created`
- `activation_validated`
- `activation_released`
- `activation_denied`

### `admin_users`

Fields:
- `id`
- `email`
- `password_hash`
- `role`
- `status`
- `created_at`
- `updated_at`

## License Key Format

Do not reuse the current deterministic local MD5 style.

Recommended format:

- Human-friendly segmented key
- Example: `GRP-EMAIL-7X4P-Q9KD-3M2V`

Requirements:
- Randomly generated on server
- Not derivable from machine ID
- Unique index in database
- Product prefix optional but useful for support

## Device Fingerprint Strategy

The client should send a stable machine fingerprint, not only a raw OS serial when possible.

Recommended email-tool fingerprint payload:

- `machine_id`
- `machine_name`
- `os_name`
- `os_version`
- `app_version`

For the first iteration, reusing the current machine ID extraction is acceptable.
Later, normalize the fingerprint strategy across all products via a shared client SDK.

## API Design

### 1. Activate

`POST /api/v1/licenses/activate`

Request:

```json
{
  "product_code": "globalreach_pro",
  "license_key": "GRP-EMAIL-7X4P-Q9KD-3M2V",
  "machine_id": "CYFVK1G3PP",
  "machine_name": "Aidi-MacBook",
  "os_name": "macOS",
  "os_version": "15.4",
  "app_version": "2026.04.14"
}
```

Success response:

```json
{
  "ok": true,
  "license_status": "active",
  "activation_status": "active",
  "activation_token": "act_xxx",
  "expires_at": "2027-04-14T00:00:00Z",
  "plan_name": "single-device",
  "max_activations": 1,
  "message": "Activation successful."
}
```

Failure response:

```json
{
  "ok": false,
  "code": "activation_limit_reached",
  "message": "This license has reached the activation limit."
}
```

### 2. Validate

`POST /api/v1/licenses/validate`

Request:

```json
{
  "product_code": "globalreach_pro",
  "license_key": "GRP-EMAIL-7X4P-Q9KD-3M2V",
  "activation_token": "act_xxx",
  "machine_id": "CYFVK1G3PP",
  "app_version": "2026.04.14"
}
```

Success response:

```json
{
  "ok": true,
  "license_status": "active",
  "activation_status": "active",
  "expires_at": "2027-04-14T00:00:00Z",
  "message": "License is valid."
}
```

Failure codes:
- `invalid_license`
- `product_mismatch`
- `machine_mismatch`
- `license_disabled`
- `license_expired`
- `activation_not_found`

### 3. Release Activation

`POST /api/v1/licenses/release`

Request:

```json
{
  "product_code": "globalreach_pro",
  "license_key": "GRP-EMAIL-7X4P-Q9KD-3M2V",
  "machine_id": "CYFVK1G3PP"
}
```

Response:

```json
{
  "ok": true,
  "message": "Activation released."
}
```

### 4. Admin Create License

`POST /api/v1/admin/licenses`

Request:

```json
{
  "product_code": "globalreach_pro",
  "customer_id": 12,
  "plan_name": "single-device",
  "max_activations": 1,
  "expires_at": "2027-04-14T00:00:00Z",
  "notes": "Email tool annual plan"
}
```

Response:

```json
{
  "ok": true,
  "license_key": "GRP-EMAIL-7X4P-Q9KD-3M2V"
}
```

### 5. Admin Disable License

`POST /api/v1/admin/licenses/{id}/disable`

### 6. Admin Extend License

`POST /api/v1/admin/licenses/{id}/extend`

### 7. Admin Reset Activations

`POST /api/v1/admin/licenses/{id}/reset-activations`

## Admin Console Modules

### Product Management

Used by internal staff only.

Capabilities:
- Create product
- Disable product
- View product list

### License Management

Capabilities:
- Create license
- Search by key / customer / product
- Disable license
- Extend expiration
- Change activation limit
- Add internal notes

### Activation Management

Capabilities:
- View current activated devices
- Release a specific device
- Reset all activations under a license
- Inspect last validation time

### Audit Log

Capabilities:
- Filter by license key
- Filter by admin user
- Filter by date
- See activation and release history

## Email Tool Client Integration

## Current State

The current email tool uses local-only validation in:

- [`app/services/license_service.py`](/Users/aidi/群发工具/app/services/license_service.py)
- [`main.py`](/Users/aidi/群发工具/main.py)

That logic should be replaced with a client API layer.

## Recommended Client Refactor

### New Local State Keys

Store these in local app state:

- `license_key`
- `license_machine_id`
- `license_activation_token`
- `license_status`
- `license_verified_at`
- `license_expires_at`
- `license_last_error`

### New Client Service

Add a new service module, for example:

- `app/services/license_client.py`

Responsibilities:
- Build activation requests
- Call `activate`
- Call `validate`
- Call `release`
- Normalize API errors

### Activation Flow

1. App starts
2. Read cached `license_key`, `activation_token`, `machine_id`
3. Call `validate`
4. If valid, enter app
5. If invalid, show activation dialog
6. User enters `License Key`
7. Client calls `activate`
8. Save token + status + expiry locally
9. Enter app

### Activation Dialog Changes

Keep the existing dialog pattern but change wording:

- Show machine ID
- Input should say `License Key`
- Status should show API error messages

### Offline Handling

Recommended first version:
- Require internet on first activation
- Allow short grace-period validation cache afterward

Recommended local fallback:
- If last validation succeeded within 3 to 7 days, allow temporary access
- Revalidate when network returns

Do not implement indefinite offline trust for commercial licenses.

## Security Notes

### Avoid

- Client-side deterministic license generation
- Shipping secret salts in desktop clients
- Accepting license validity without server confirmation forever
- Storing raw admin secrets in the client

### Recommended

- Server-generated random keys
- Signed activation tokens
- HTTPS only
- Admin auth with RBAC
- Audit log on all admin actions
- Rate limiting on activation endpoints

## Migration Plan

### Phase 1

Build standalone backend and admin UI:
- products
- license keys
- activations
- admin login
- create/disable/extend/reset APIs

### Phase 2

Add email-tool client integration:
- `license_client.py`
- activation dialog changes
- validate on startup
- local state caching

### Phase 3

Deprecate the current local MD5 activation:
- keep temporary compatibility flag
- migrate internal licenses
- remove local-only generation after stable rollout

### Phase 4

Onboard next products:
- assign `product_code`
- reuse same endpoints
- reuse same admin platform

## First Deliverables

If building this now, the recommended first implementation set is:

1. PostgreSQL schema for `products`, `license_keys`, `license_activations`, `license_events`
2. Admin login
3. License creation page
4. Activation lookup page
5. `activate` API
6. `validate` API
7. `release` API
8. Email tool client integration

## Suggested Repo Split

If kept separate from the email tool:

- `license-platform/`
  - `apps/api`
  - `apps/admin`
  - `packages/sdk`
  - `packages/shared`

This keeps future products from depending on the email-tool repository.

## Recommended Next Step

Start with a standalone `license-platform` project and treat the email tool as an external client.
Do not continue investing in the current local-only activation algorithm except as a temporary compatibility fallback.
