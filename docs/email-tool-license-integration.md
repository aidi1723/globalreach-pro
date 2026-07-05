# Email Tool License Integration

## Current Decision

The formal activation plan is now documented in:

- [`docs/unified-server-license-plan.md`](/Users/aidi/群发工具/docs/unified-server-license-plan.md)

This file only describes the current client integration status.

Production rule:

- customers should use server-side licensing only
- local activation remains internal-only for development or emergency fallback

## Runtime Behavior

The current client still supports two runtime modes:

1. If `GLOBALREACH_LICENSE_API_BASE_URL` and `GLOBALREACH_LICENSE_PRODUCT_CODE` are configured,
   use server-mode activation.
2. Otherwise, fall back to the current local activation algorithm.

This dual-mode behavior exists for transition compatibility.
It should not be interpreted as "both modes are equal production options".

## Current Client Files

- [`app/services/license_service.py`](/Users/aidi/群发工具/app/services/license_service.py)
- [`app/services/license_api_client.py`](/Users/aidi/群发工具/app/services/license_api_client.py)
- [`main.py`](/Users/aidi/群发工具/main.py)

## Local State Keys

- `license_key`
- `license_machine_id`
- `license_activation_token`
- `license_status`
- `license_expires_at`
- `license_last_error`
- `license_verified_at`
- `license_provider`
- `license_api_base_url`
- `license_product_code`

## Environment Variables

- `GLOBALREACH_LICENSE_API_BASE_URL`
- `GLOBALREACH_LICENSE_PRODUCT_CODE`

## Next Implementation Steps

1. Finish production deployment of `license-platform`.
2. Point the email tool to the production server and product code `globalreach_pro`.
3. Remove customer-facing language that suggests local activation is a standard option.
4. Add release-device UI only if customer support later needs self-service unbinding.
5. Add grace-period behavior for offline validation if production requirements demand it.

## Current Integration Reality

- The email tool client can already switch between local activation and server mode.
- The standalone `license-platform` MVP already exposes aligned activate, validate, release, and admin endpoints.
- A local end-to-end check can now be run with `tools/license_server_e2e.py`.
- Production deployment is still a separate step; local integration success does not mean the public server is already online.
- The target long-term path is one shared server license platform for both the email tool and future products.
