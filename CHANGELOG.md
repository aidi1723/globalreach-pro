# Changelog

All notable public changes are recorded here.

This project currently uses date-based release notes until a formal semantic versioning policy is adopted.

## Unreleased

- No unreleased changes.

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
