# Release Handoff

## Current Status

GlobalReach PRO is ready as a GPLv3 open-source repository.

- Public repository: `https://github.com/aidi1723/globalreach-pro`
- Branch: `main`
- Current release stage: initial open-source publication
- License: GNU GPL version 3 only
- Runtime mode: open-source desktop mode by default when no server-license endpoint is configured
- Optional commercial/server-license path: `license-platform/`

## What Was Completed

- Added GPLv3 `LICENSE` and project `NOTICE`.
- Reviewed and updated README, security notes, release checklist, maintenance guide, changelog, and handoff notes.
- Confirmed runtime databases, local environments, build outputs, logs, caches, and private `.env` files are ignored.
- Added development dependency file and CI workflow.
- Fixed CI compatibility with newer FastAPI/Starlette route internals.
- Updated GitHub Actions to current major versions.

## Final Verification Record

Latest verified commands:

```bash
python -m compileall -q app license-platform/apps/api/app main.py
python -m pytest -q
git diff --check
```

Additional release checks:

```bash
git ls-files | rg '(^|/)(\.venv|__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|build|dist|node_modules|\.DS_Store)(/|$)|\.pyc$|\.sqlite3?$|\.db$|\.egg-info'
rg -n '(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|password\s*=\s*['"'"'"][^'"'"'"]+|api[_-]?key\s*=\s*['"'"'"][^'"'"'"]+|secret\s*=\s*['"'"'"][^'"'"'"]+)' app license-platform tests README.md docs .github requirements.txt requirements-dev.txt LICENSE NOTICE
```

Expected release-check result:

- tracked-file scan prints no output
- secret scan only reports deliberate dummy values in tests

GitHub Actions:

- Python `3.11`: passed
- Python `3.12`: passed

## Maintenance Owner Path

Use `MAINTENANCE.md` as the ongoing owner guide.

Primary paths:

- Desktop app: `main.py`, `app/`, `tools/build_desktop.py`
- License platform: `license-platform/`, `docs/license-platform-*.md`
- Public docs: `README.md`, `CHANGELOG.md`, `SECURITY.md`, `OPEN_SOURCE_CHECKLIST.md`

## Residual Risks

These are known and documented, not blockers for source publication:

- SMTP account-pool passwords are still stored in the local app database as application data; use OS keychain/keyring before distributing to non-technical users.
- The project does not provide unsubscribe hosting, bounce handling, open/click tracking, complaint handling, or deliverability guarantees.
- Operators remain responsible for recipient consent, suppression lists, provider terms, and anti-spam/privacy compliance.
- The license platform is an MVP suitable for controlled deployment, not a fully hardened SaaS control plane.
- Screenshots and fake sample data are still optional follow-up items.

## Next Actions

Recommended next actions after this handoff:

1. Create a GitHub release or tag when choosing the first formal version name.
2. Add screenshots and sample lead data only after confirming they contain no private information.
3. Add a contribution guide if outside contributors are expected.
4. Prioritize keychain/keyring storage and suppression-list support before positioning the app for broad production sending.
