# Release Handoff

## Current Status

GlobalReach PRO is published as a GPLv3 open-source repository and has completed the `v0.2.0` sending-governance phase.

- Public repository: `https://github.com/aidi1723/globalreach-pro`
- Branch: `main`
- Latest release tag: `v0.2.0`
- Latest release commit: `ca0b236 Avoid credential-like test placeholders`
- License: GNU GPL version 3 only
- Runtime mode: open-source desktop mode by default when no server-license endpoint is configured
- Optional commercial/server-license path: `license-platform/`

## What Was Completed

- Published the source under GPLv3 with `LICENSE`, `NOTICE`, security notes, checklist, maintenance guide, changelog, and handoff notes.
- Added CI and development dependency documentation for the Python test suite.
- Added optional FastAPI license-platform documentation and deployment notes.
- Added sending governance for controlled production use:
  - suppression-entry storage and service layer
  - duplicate-recipient policy integration
  - per-account rolling daily and hourly quota checks
  - canonical UTC quota timestamp storage and query
  - legacy quota backfill from historical send results
  - pause/resume for batch-send tasks
  - dataset validation before resuming paused tasks
  - desktop controls for account limits, pause, resume, stop, and result refresh
- Added technical documentation in `docs/sending-governance.md`.
- Added next-phase direction in `ROADMAP.md`.

## Final Verification Record

Latest verified release commands:

```bash
python -m compileall -q app license-platform/apps/api/app main.py
python -m pytest -q -rs
git diff --check
```

Release-hardening checks:

```bash
git ls-files | rg '(^|/)(\.venv|__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|build|dist|node_modules|\.DS_Store)(/|$)|\.pyc$|\.sqlite3?$|\.db$|\.egg-info'
rg -n '(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|password\s*=\s*['"'"'"][^'"'"'"]+|api[_-]?key\s*=\s*['"'"'"][^'"'"'"]+|secret\s*=\s*['"'"'"][^'"'"'"]+)' app license-platform tests README.md docs .github requirements.txt requirements-dev.txt LICENSE NOTICE
```

Expected release-check result:

- tracked-file scan prints no output
- secret scan prints no output

Most recent local verification:

- `compileall`: passed
- `pytest -q -rs`: `119 passed`
- `git diff --check`: passed
- generated-file scan: no output
- secret-pattern scan: no output

## Maintenance Owner Path

Use `MAINTENANCE.md` as the ongoing owner guide.

Primary paths:

- Desktop app: `main.py`, `app/`, `tools/build_desktop.py`
- Sending governance: `app/services/send_policy.py`, `app/services/send_quota.py`, `app/services/suppression.py`, `app/services/batch_sender.py`, `app/storage/db.py`, `docs/sending-governance.md`
- License platform: `license-platform/`, `docs/license-platform-*.md`
- Public docs: `README.md`, `CHANGELOG.md`, `SECURITY.md`, `OPEN_SOURCE_CHECKLIST.md`, `ROADMAP.md`

## Residual Risks

These are known and documented, not blockers for controlled small-scale production use:

- SMTP account-pool passwords are still stored in the local app database as application data; use OS keychain/keyring before distributing to non-technical users.
- SMTP delivery and local result/quota persistence are not one atomic transaction around the external SMTP side effect.
- The app does not provide hosted unsubscribe links, bounce ingestion, open/click tracking, complaint handling, or deliverability guarantees.
- Basic manual desktop suppression management exists; CSV import/export, search, and bulk review are still follow-up items.
- Older paused tasks without a stored dataset fingerprint fall back to source path and row-count validation.
- Legacy naive timestamps are interpreted as local time during quota backfill.
- Operators remain responsible for recipient consent, suppression lists, provider terms, and anti-spam/privacy compliance.
- The license platform is an MVP suitable for controlled deployment, not a fully hardened SaaS control plane.

## Next Actions

Recommended next actions after this handoff:

1. Add OS keychain/keyring storage for SMTP account-pool passwords.
2. Expand the desktop suppression-list screen with CSV import/export, search, and bulk review.
3. Add fake sample lead data and screenshots after confirming they contain no private information.
4. Add a pre-send governance summary before SMTP delivery starts.
5. Add bounce/complaint/unsubscribe import paths for post-send reconciliation.
6. Follow `ROADMAP.md` for the next development phase.
