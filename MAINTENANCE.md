# Maintenance Guide

This document is the operational path for maintaining GlobalReach PRO after the GPLv3 open-source release.

## Repository

- Public repository: `https://github.com/aidi1723/globalreach-pro`
- Primary branch: `main`
- License: GNU GPL version 3 only. See `LICENSE` and `NOTICE`.
- Supported Python versions in CI: `3.11` and `3.12`

## Maintenance Tracks

### Desktop App

Scope:

- email list import and field mapping
- template rendering
- AI draft generation
- SMTP account testing and batch sending
- desktop packaging

Key paths:

- `main.py`
- `app/services/`
- `app/controllers/`
- `app/ui/`
- `app/storage/`
- `tools/build_desktop.py`
- `docs/desktop-packaging.md`

Before changing this track, run:

```bash
python -m pytest tests/test_ai_writer.py tests/test_batch_sender.py tests/test_smtp_service.py tests/test_template.py tests/test_importer.py tests/test_license_service.py
```

### License Platform

Scope:

- public activation, validation, and release APIs
- admin API
- server-rendered admin console
- migration and import tooling
- desktop client integration

Key paths:

- `license-platform/apps/api/app/`
- `license-platform/database/`
- `license-platform/tools/`
- `docs/license-platform-deployment.md`
- `docs/license-platform-api-examples.md`
- `docs/license-platform-legacy-migration.md`
- `docs/email-tool-license-integration.md`

Before changing this track, run:

```bash
python -m pytest tests/test_license_platform_auth.py tests/test_license_platform_console_and_migration.py tests/test_license_platform_db.py tests/test_license_platform_rate_limit.py tests/test_license_api_client.py
```

### Documentation

Scope:

- public README and release notes
- open-source checklist
- maintenance, security, packaging, and deployment docs

Key paths:

- `README.md`
- `CHANGELOG.md`
- `RELEASE_HANDOFF.md`
- `OPEN_SOURCE_CHECKLIST.md`
- `SECURITY.md`
- `docs/`
- `license-platform/README.md`

When documentation changes affect commands, environment variables, or behavior, verify the related code or tests before publishing the docs.

## Standard Verification

Use this as the default pre-commit check:

```bash
python -m compileall -q app license-platform/apps/api/app main.py
python -m pytest -q
git diff --check
```

For release readiness, also check that generated and sensitive files are not tracked:

```bash
git ls-files | rg '(^|/)(\.venv|__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|build|dist|node_modules|\.DS_Store)(/|$)|\.pyc$|\.sqlite3?$|\.db$|\.egg-info'
rg -n '(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|password\s*=\s*['"'"'"][^'"'"'"]+|api[_-]?key\s*=\s*['"'"'"][^'"'"'"]+|secret\s*=\s*['"'"'"][^'"'"'"]+)' app license-platform tests README.md docs .github requirements.txt requirements-dev.txt LICENSE NOTICE
```

Expected result:

- tracked-file scan prints no output
- secret scan may only print deliberate dummy values in tests

## Release Path

1. Update `CHANGELOG.md` with user-visible changes.
2. Run the standard verification commands.
3. Confirm `OPEN_SOURCE_CHECKLIST.md` has no unchecked blocking items.
4. Commit changes to `main`.
5. Push and wait for GitHub Actions to pass on Python `3.11` and `3.12`.
6. For a public release tag, use a clear version name such as `v2026.07.05` or a semantic version once the project adopts one.
7. If shipping binaries, publish the corresponding source for the exact released version under GPLv3.

## Security Maintenance

- Never commit `.env` files with real values.
- Never commit SMTP credentials, AI API keys, license keys, activation tokens, lead lists, customer data, or send history.
- Keep runtime databases out of Git:
  - `app/storage/*.db`
  - `app/storage/*.sqlite`
  - `app/storage/*.sqlite3`
  - `license-platform/data/`
- Before distributing desktop builds to non-technical users, prioritize OS keychain/keyring storage for SMTP account-pool passwords.

## Known Follow-Up Queue

These are not blockers for the current open-source release, but they are the next responsible maintenance items:

- add OS keychain/keyring storage for SMTP account-pool passwords
- add suppression-list support before positioning the app as a production outreach sender
- add screenshots using fake data only
- add a sample lead CSV with fake data
- add `CONTRIBUTING.md` if outside contributors are expected
- add release tags once the first formal version number is chosen
- decide whether the license platform should remain in this repository long term or move to its own repository
