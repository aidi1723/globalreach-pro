# Roadmap

This roadmap starts after the `v0.2.0` sending-governance release. It is intentionally practical: each phase should leave the project more usable in real operations without assuming a large SaaS rebuild.

## Current Production Position

The app is ready for controlled, small-scale production use:

- desktop lead import and template rendering are in place
- SMTP account pool sending is supported
- duplicate policy, suppression checks, quota checks, pause, and resume are implemented
- release verification passed with the full automated test suite

It should not yet be positioned as a large-scale email marketing platform because unsubscribe hosting, bounce handling, complaint handling, deliverability analytics, and encrypted credential storage are still outside the current product.

## Phase 1: Operational Hardening

Goal: make daily use safer before increasing send volume.

Recommended work:

- Add OS keychain/keyring storage for SMTP account-pool passwords.
- Expand the desktop suppression-list screen with CSV import/export, search, and bulk review.
- Add a small fake sample lead CSV for onboarding and tests.
- Add fake-data screenshots for README and release pages.
- Add a pre-send governance summary that shows expected `send`, `review`, `suppressed`, and likely duplicate counts before the operator starts a batch.

Acceptance signal:

- A non-technical operator can configure accounts, import fake leads, review governance warnings, and run a small batch without touching code or SQLite.

## Phase 2: Delivery Feedback Loop

Goal: help operators learn what happened after sending.

Recommended work:

- Add structured bounce/failed-delivery import from provider CSV exports.
- Add manual complaint/unsubscribe import into the suppression list.
- Add send-result filters and export for `sent`, `failed`, `suppressed`, `rate_limited`, and `review_required`.
- Add domain/account-level send summary reports.
- Add deliverability checklist docs for SPF, DKIM, DMARC, warm-up, and provider limits.

Acceptance signal:

- Operators can reconcile sends, failures, unsubscribes, and suppression updates after every campaign.

## Phase 3: Packaging and Release Discipline

Goal: make installation and updates predictable.

Recommended work:

- Build and test macOS packaging using `tools/build_desktop.py`.
- Add release artifacts only after confirming GPLv3 source availability for the exact version.
- Add `CONTRIBUTING.md` if outside contributors are expected.
- Add a lightweight release template for GitHub releases.
- Decide whether `license-platform/` stays in this repository or moves to a separate repository.

Acceptance signal:

- A tagged source release can be reproduced locally, packaged, and smoke-tested from a fresh machine.

## Phase 4: Commercial License Platform Maturity

Goal: make the optional server-license path safer for controlled commercial use.

Recommended work:

- Harden admin authentication and deployment defaults.
- Add backup/restore and migration runbooks.
- Add rate-limit and audit-log review docs.
- Add environment-specific deployment examples.
- Add integration tests for desktop license validation against the API.

Acceptance signal:

- The license platform has a documented operator path for setup, backup, incident response, and upgrade.

## Work Not Recommended Yet

Avoid these until the earlier phases are stable:

- open/click tracking
- multi-user team permissions
- full campaign-builder redesign
- high-volume send automation
- hosted unsubscribe infrastructure inside the desktop app

Those areas increase compliance and operational complexity and should be handled only after the core sender is safer for everyday use.
