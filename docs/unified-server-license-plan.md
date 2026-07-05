# Unified Server License Plan

## Decision

The long-term activation model for this project is:

- production customers use **server-side licensing only**
- local activation remains **internal-only** for development or emergency fallback
- the email tool and future tools should converge on **one shared license platform**

This is now the default maintenance rule.
Do not treat local machine-code activation as a customer-facing commercial solution.

## Products In Scope

Current and planned product codes:

- `globalreach_pro`: the desktop email sending tool in this repository
- `zhishu_lead_plugin`: the Zhishu lead-generation browser plugin

More tools can be added later, but every product must use a stable `product_code`.

## Why This Decision Was Made

Local activation is not suitable as the formal commercial path because it cannot reliably support:

- device reset by customer support
- license disable / revoke
- expiry extension and renewal
- activation history and audit trail
- multi-product management
- future bundle plans and seat management

The standalone `license-platform` already matches the direction we need:

- multi-product model
- activate / validate / release endpoints
- admin authentication
- license creation, disable, extend, and reset operations
- database-backed records instead of client-only derivation

## Formal Architecture

### Server

Use `license-platform/` as the single source of truth for commercial authorization.

Responsibilities:

- store products
- issue license keys
- bind activations to devices
- validate license state
- release or reset activations
- record admin and activation events

### Desktop Client

The email tool should run in server mode in production.

Production runtime requirements:

- `license_api_base_url`
- `license_product_code=globalreach_pro`

Client behavior:

1. on startup, load local cached license state
2. if `license_key + activation_token + machine_id` exist, call `validate`
3. if validation succeeds, continue startup
4. if validation fails or no activation exists, show the activation dialog
5. on successful activation, persist:
   - `license_key`
   - `license_machine_id`
   - `license_activation_token`
   - `license_status`
   - `license_expires_at`
   - `license_verified_at`

### Plugin Client

The Zhishu plugin should eventually move to the same platform, but with plugin-specific device identity:

- `device_id`
- `fingerprint_key`
- `product_code=zhishu_lead_plugin`

This repository does not implement the plugin migration, but the platform must remain compatible with it.

## Maintenance Rule

### What counts as production-ready

For the email tool, "done" means all of the following are true:

- `license-platform` is deployed with HTTPS
- the product `globalreach_pro` exists on the server
- the client points to the real server URL
- real customer licenses are issued from the platform
- activation and validation succeed without relying on local-only hashing

### What is allowed for local activation

Local activation may still exist in code, but only for:

- developer machines
- temporary offline debugging
- emergency recovery before the server is restored

It must not be the default customer workflow.

### Support operations that must stay available

Customer support must always be able to do these from the platform:

- create a new license
- search license by product or key
- disable a compromised license
- extend expiry
- reset all activations for a license
- inspect activation history

If a future refactor removes one of these capabilities, it is a regression.

## Product Initialization Standard

When a new product is added to the platform, define at least:

- `product_code`
- `product_name`
- default plan names
- default `max_activations`
- release notes for client integration

Recommended initial products:

- `globalreach_pro` => `GlobalReach PRO`
- `zhishu_lead_plugin` => `智枢获客插件`

## Email Tool Activation Flow

### Production flow

1. App starts.
2. App gets `machine_id`.
3. App loads `license_api_base_url` and `license_product_code`.
4. If server mode is configured and cached `activation_token` exists, call `/api/v1/licenses/validate`.
5. If validation returns active, continue startup.
6. If validation fails, show activation dialog.
7. User enters the server-issued `license_key`.
8. App calls `/api/v1/licenses/activate`.
9. App stores returned `activation_token` and status fields.
10. Future startups validate instead of re-activating.

### Failure handling

- If activation returns invalid key, show a customer-readable error and keep the app locked.
- If activation limit is reached, customer support should reset activations server-side instead of editing local files.
- If the server is temporarily unavailable, log the failure and keep the app locked unless an explicit internal fallback mode is enabled.

## Device Identity Rule

For the desktop email tool, the current first version uses `machine_id` from the client.

That is acceptable for now.
Do not redesign the client-side identity scheme unless one of these becomes necessary:

- one machine is being misidentified too often
- cross-platform packaging changes the identifier stability
- we need hardware replacement tolerance without full reactivation

If identity changes in the future, keep backward compatibility or provide a one-time migration path.

## Migration Plan

### Phase 1

Make `globalreach_pro` production-ready on `license-platform`.

Tasks:

- deploy the API
- create admin user
- create product record
- generate real licenses
- point the email tool to the production server

### Phase 2

Stop treating local activation as a customer path.

Tasks:

- remove local-activation language from customer docs
- distribute only server-issued license keys
- keep local fallback undocumented for external users

### Phase 3

Migrate the Zhishu plugin from the old Node.js license server to `license-platform`.

Tasks:

- add `zhishu_lead_plugin`
- define plugin device binding rules
- switch plugin activate / validate calls
- retire the old single-product license service after data migration

## Files Related To This Plan

- [`main.py`](/Users/aidi/群发工具/main.py)
- [`app/services/license_api_client.py`](/Users/aidi/群发工具/app/services/license_api_client.py)
- [`app/services/license_service.py`](/Users/aidi/群发工具/app/services/license_service.py)
- [`docs/email-tool-license-integration.md`](/Users/aidi/群发工具/docs/email-tool-license-integration.md)
- [`docs/license-platform-design.md`](/Users/aidi/群发工具/docs/license-platform-design.md)
- [`docs/license-platform-deployment.md`](/Users/aidi/群发工具/docs/license-platform-deployment.md)
- [`docs/server-license-rollout-checklist.md`](/Users/aidi/群发工具/docs/server-license-rollout-checklist.md)

## Maintenance Reminder

If future work conflicts with this document, prefer these rules:

1. server-side licensing is the official path
2. `license-platform` is the shared platform
3. product identity is explicit via `product_code`
4. local activation is internal-only
