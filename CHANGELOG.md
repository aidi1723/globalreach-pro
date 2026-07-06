# Changelog

All notable public changes are recorded here.

This project currently uses date-based release notes until a formal semantic versioning policy is adopted.

## Unreleased

- Completed handoff, roadmap, and sending-governance documentation updates after the `v0.2.0` tag.
- Added `DESIGN.md` as the desktop UI design baseline.
- Added a preflight/send governance summary panel.
- Added basic desktop suppression-list controls for manual add, remove, refresh, count, and list review.
- Added a compact task summary label above batch-send task logs.

## 2026-07-06 - v0.2.0 Sending Governance Release

### Added

- Added local suppression-entry storage and service support.
- Added per-account rolling 24-hour and rolling 1-hour send quota enforcement.
- Added send-policy decisions for invalid email, suppression, duplicate review/skip, rate limit, and eligible send.
- Added pause and resume support for batch-send tasks.
- Added dataset source, row-count, and fingerprint validation before resuming paused tasks.
- Added desktop controls for daily/hourly account limits, pause, resume, stop, and task-result refresh.
- Added focused tests for suppression, quota, send policy, governance-aware batch sending, and controller behavior.

### Changed

- Batch sending now evaluates governance decisions before SMTP delivery and records explicit row outcomes.
- Quota timestamps are stored and queried in canonical UTC form.
- Legacy `send_results` are backfilled into account quota usage for existing installations.
- Legacy naive timestamps are interpreted as local time during quota backfill.

### Fixed

- Fixed quota timestamp deduplication during backfill.
- Fixed pause-during-delay behavior so the next row is not sent after pause is requested.
- Fixed resume safety for mismatched dataset source, row count, or fingerprint.
- Replaced credential-like test placeholders so repository secret scans are clean.

### Verification

- Local release verification passed with `119 passed`.
- `compileall`, whitespace checks, generated-file scan, and secret-pattern scan passed.
- Published tag: `v0.2.0`.

## 2026-07-05 - GPLv3 Open-Source Release

### Added

- Published the project under GNU GPL version 3 only.
- Added open-source release documentation, security policy, release checklist, maintenance guide, and handoff record.
- Added GitHub Actions test workflow for Python `3.11` and `3.12`.
- Added `requirements-dev.txt` for full test and license-platform dependencies.
- Added optional FastAPI license-platform documentation and deployment notes.

### Changed

- Documented open-source desktop behavior when no server-license configuration is present.
- Clarified that legacy local licensing is private backward-compatibility only and disabled by default.
- Updated CI actions to current major versions.

### Fixed

- Fixed the license-platform route test so it works with newer FastAPI/Starlette route internals.
- Improved failing subprocess test output for easier CI diagnosis.

### Verification

- Local tests passed with `60 passed, 1 skipped`.
- Clean temporary environment tests passed with `63 passed`.
- GitHub Actions passed on Python `3.11` and `3.12`.
