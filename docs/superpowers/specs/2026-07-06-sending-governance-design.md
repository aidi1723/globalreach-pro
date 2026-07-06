# Sending Governance Design

## Purpose

Move GlobalReach PRO from a basic SMTP batch sender toward a safer production outreach workbench. This phase focuses on deciding whether a recipient is eligible to receive mail, controlling send volume, and making interrupted tasks recoverable. It does not add new AI writing features or analytics tracking.

## Goals

- Prevent sends to recipients that should not be contacted.
- Make duplicate, skipped, blocked, failed, paused, and sent outcomes explicit.
- Add account-level send limits before each SMTP send attempt.
- Allow a batch task to pause and resume without re-sending completed rows.
- Keep all governance decisions testable outside the UI.

## Non-Goals

- Hosted unsubscribe-link service.
- Bounce, open, click, or complaint tracking.
- New marketing campaign builder.
- Multi-user permission model.
- License-platform changes.

## Approach

Implement a small governance layer between imported lead rows and SMTP delivery:

1. `SuppressionService` manages normalized recipient addresses that must not be contacted.
2. `SendPolicyService` evaluates each row and returns a structured decision: `send`, `skip_duplicate`, `review_required`, `suppressed`, `invalid_email`, or `rate_limited`.
3. `SendQuotaService` tracks account usage per rolling day and optional per-hour windows.
4. `BatchSender` consumes decisions and persists every row outcome before moving to the next row.
5. The UI displays governance counts and exposes suppression-list import/export and task pause/resume controls.

This keeps policy decisions separate from SMTP delivery, so unit tests can cover risky branches without network access.

## Data Model

Add desktop SQLite tables:

- `suppression_entries`
  - `id`
  - `recipient_email`
  - `reason`
  - `source`
  - `created_at`
  - unique index on normalized `recipient_email`

- `account_send_usage`
  - `id`
  - `account_label`
  - `recipient_email`
  - `task_id`
  - `sent_at`
  - indexes on `account_label, sent_at` and `recipient_email`

Extend existing task/result records:

- `send_tasks.status`: add `paused`
- `send_results.status`: add `suppressed`, `rate_limited`, and `pending_resume`
- Preserve existing `sent`, `failed`, `skipped_duplicate`, and `review_required`

## Batch Flow

1. Create or resume a task.
2. For each row not already recorded for that task:
   - Normalize recipient email.
   - Check suppression list.
   - Check duplicate history using existing sent-result history.
   - Check account quota before SMTP delivery.
   - Persist non-send outcomes immediately.
   - If eligible, attempt SMTP send and record success or failure.
3. If pause is requested, mark the task `paused` after the current row finishes.
4. Resume starts from rows without a result for the task.

Stop remains a terminal operator action. Pause is resumable.

## UI Changes

Add a compact governance section in the existing desktop workflow:

- Suppression list: import CSV, add single email, remove email, export CSV.
- Send limits: per-account daily limit and optional hourly limit.
- Task controls: pause, resume, stop.
- Task summary: sent, failed, skipped, review, suppressed, rate-limited, pending.

The first implementation should reuse the existing CustomTkinter style and avoid a broad UI redesign.

## Error Handling

- Invalid suppression CSV rows are reported with counts and examples.
- Missing or malformed send limits block task start with a clear message.
- Rate-limited rows are not sent and are recorded as `rate_limited`.
- Resume ignores rows already recorded for the same task.
- If quota state cannot be read, fail closed and block sending rather than sending unchecked.

## Testing

Add focused tests for:

- Suppression normalization and import/export.
- Policy decisions for suppressed, invalid, duplicate, review, and eligible rows.
- Account daily/hourly quota boundaries.
- Batch pause/resume without duplicate sends.
- Task/result status summaries for all new statuses.
- Storage migrations for new tables and columns.

Run the existing standard verification after implementation:

```bash
python -m compileall -q app license-platform/apps/api/app main.py
python -m pytest -q
git diff --check
```

## Rollout Plan

Implement in four increments:

1. Storage and service layer for suppression entries and quota usage.
2. Send policy decisions with unit tests.
3. Batch sender pause/resume and new statuses.
4. UI controls and documentation updates.

Each increment should keep the full test suite green before moving to the next one.
