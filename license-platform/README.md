# License Platform

Standalone multi-product license platform.

This project is intended to serve:

- `globalreach_pro`
- future desktop tools
- future plugin systems

## Structure

- `apps/api`
  Public and admin API service
- `apps/admin`
  Admin console notes. The current MVP uses server-rendered console pages from `apps/api`.
- `packages/sdk`
  Future shared client SDK notes
- `database`
  SQL schema and migration bootstrap notes

## Runtime Stack

- Python 3.11+
- FastAPI
- SQLite for local development or single-node MVP deployments
- PostgreSQL for production-style deployments
- Alembic
- Jinja2 server-rendered admin console

## First Milestones

1. Bring up API health endpoint
2. Create products and licenses
3. Activate / validate / release flows
4. Admin search and activation reset
5. Email tool integration

## Current MVP Status

Implemented:

- sqlite and PostgreSQL runtime database support
- Alembic migration scaffold and migration runner
- admin create/list/disable/extend/reset endpoints
- public activate/validate/release endpoints
- server-rendered login page and admin dashboard at `/console/login` and `/console`
- product management, license creation, batch license actions, CSV export, and backup export in the console
- development run script
- seed script for demo licenses

Useful files:

- `apps/api/app/main.py`
- `apps/api/app/auth.py`
- `apps/api/app/services/admin_users.py`
- `apps/api/app/services/license_manager.py`
- `tools/run_api.py`
- `tools/run_migrations.py`
- `tools/create_admin_user.py`
- `tools/generate_admin_token.py`
- `tools/import_legacy_licenses.py`
- `tools/seed_demo_data.py`
- `../tools/license_server_e2e.py`
- `../docs/license-platform-api-examples.md`
- `../docs/license-platform-deployment.md`
- `../docs/license-platform-legacy-migration.md`

## Local Run Notes

- `tools/run_api.py` defaults to `reload=False`, which is safer in restricted environments.
- Set `LICENSE_PLATFORM_ADMIN_AUTH_SECRET` and use admin email/password login for the admin console and admin API.
- When `LICENSE_PLATFORM_ENV` is not `development`, startup now requires `LICENSE_PLATFORM_ADMIN_AUTH_SECRET`.
- Run `tools/run_migrations.py upgrade head` before first production start when using a fresh database.
- Use `../tools/license_server_e2e.py` for a repeatable `create -> activate -> validate -> release` integration check.
