# Sending Governance

This document describes the production-safety layer added in `v0.2.0`.

## Purpose

Sending governance controls whether a row is eligible for SMTP delivery before the app attempts to send email. It is designed to reduce accidental duplicate outreach, respect suppression records, and keep each SMTP account inside operator-defined volume limits.

This is not a deliverability or compliance platform. Operators still need consent, unsubscribe handling, bounce monitoring, complaint handling, and provider-term compliance outside this desktop app.

## Runtime Flow

The batch sender evaluates each imported row in this order:

1. Normalize and validate the recipient email.
2. Check the local suppression list.
3. Apply duplicate-recipient policy from historical send records.
4. Check the selected SMTP account's rolling send quota.
5. Attempt SMTP delivery only when the policy decision is `send`.
6. Persist one row result before moving to the next row.

Non-send outcomes are recorded explicitly. Current statuses include:

- `sent`
- `failed`
- `skipped_duplicate`
- `review_required`
- `suppressed`
- `rate_limited`

## Core Components

- `app/services/suppression.py`
  - Normalizes recipient addresses.
  - Adds, removes, lists, imports, and exports suppression entries.
  - Accepts CSV columns named `email` or `recipient_email`, plus optional `reason` and `source`.

- `app/services/send_quota.py`
  - Enforces rolling 24-hour and rolling 1-hour per-account limits.
  - Stores quota timestamps in canonical UTC form.
  - Treats `0` limits as disabled.

- `app/services/send_policy.py`
  - Combines invalid-email, suppression, duplicate, and quota checks into one `SendDecision`.
  - Fails closed for unknown duplicate policies by returning `review_required`.

- `app/services/batch_sender.py`
  - Applies policy decisions before SMTP delivery.
  - Records suppression, duplicate, review, rate-limit, success, and failure outcomes.
  - Supports pause/resume without re-sending rows that already have a result for the same task.

- `app/storage/db.py`
  - Creates and migrates `suppression_entries`.
  - Creates and backfills `account_send_usage`.
  - Extends task metadata with resumability fields such as source path, row count, and dataset fingerprint.

## Desktop Controls

The desktop batch-send panel exposes:

- `每日/账号(0=不限制)` for rolling 24-hour account quota.
- `每小时/账号(0=不限制)` for rolling hourly account quota.
- `暂停任务` to pause after the current send or during the inter-email delay.
- `恢复任务` to resume the latest paused task for the currently loaded dataset.
- `停止当前任务` as a terminal operator action.
- A governance summary panel showing duplicate policy, quota settings, suppression count, and latest task status.
- A basic suppression-list panel for manual add, remove, refresh, count, and compact list review.

CSV import/export, search, and bulk suppression management remain follow-up UI items.

## Resume Rules

Only paused tasks are resumable.

Resume validates:

- current loaded dataset source path
- row count
- dataset fingerprint when available

When resuming, rows that already have a result for the task are skipped. This prevents re-sending completed rows after an interruption.

Older paused tasks without a stored dataset fingerprint fall back to source path and row-count validation.

## Quota Timestamp Rules

New quota usage is stored as canonical UTC timestamps without timezone suffixes. Offset-aware timestamps are converted to UTC before storage and comparison.

Legacy usage backfilled from `send_results` is migrated into `account_send_usage`. Legacy naive timestamps are interpreted as local time during migration, then canonicalized for quota queries.

## Known Operational Limits

- SMTP delivery and local result/quota persistence cannot be one atomic transaction because SMTP is an external side effect.
- The app does not host unsubscribe links or automatically ingest bounces, complaints, opens, or clicks.
- Local suppression support is present, but a first-class desktop suppression management UI is still a follow-up item.
- SMTP credential hardening with OS keychain/keyring remains a priority before distributing builds to non-technical users.

## Verification

Use the standard release verification after changing this area:

```bash
python -m compileall -q app license-platform/apps/api/app main.py
python -m pytest -q -rs
git diff --check
```

Focused tests:

```bash
python -m pytest -q tests/test_suppression.py tests/test_send_quota.py tests/test_send_policy.py tests/test_batch_sender_governance.py tests/test_controllers.py
```
