# UI Governance Workbench Design

## Purpose

Improve the desktop UI for controlled production sending. The work should make send governance visible and operable without changing core sending behavior.

## Scope

This phase covers the existing CustomTkinter desktop app:

- Add a clear governance summary near the preflight/send area.
- Add desktop controls for local suppression-list management.
- Make batch task status easier to scan.
- Introduce shared UI helpers/tokens where they reduce repeated styling.

This phase does not add a new web UI, change routing, add analytics, or redesign the full application shell.

## Design Direction

Use `DESIGN.md` as the visual source of truth. The interface should feel like a quiet operations console:

- dark, compact panels
- direct Chinese labels
- strong contrast for status text
- clear danger/warning/success colors
- stable control dimensions

## Functional Requirements

### Governance Summary

The preflight/send area should show a compact summary panel with the current sending controls and governance state:

- duplicate policy
- daily per-account quota
- hourly per-account quota
- suppression-entry count
- latest task status when available

The summary can be computed from local UI state and storage. It does not need to run a full dry-run send simulation in this phase.

### Suppression Management

Add a suppression-list panel in the preflight/send area with:

- single email input
- reason input
- source input
- add button
- remove button
- refresh button
- count label
- compact list review textbox

CSV import/export file dialogs are not required in this phase. The service already supports CSV, but this UI phase should focus on safe manual management and visibility.

### Task Status

The task status panel should remain text-based but be more structured:

- keep the current log/status textbox
- add a compact label above or near it that summarizes the latest task and outcome counts
- keep existing start, stop, pause, resume, and refresh behavior

## Data Flow

- The UI uses `SuppressionService(app.storage)` for add/remove/list.
- Count and list refreshes read from storage through the service.
- Governance summary reads current widgets and latest send task from storage.
- Existing controller functions remain responsible for batch send start, pause, resume, stop, and refresh.

## Error Handling

- Invalid suppression email shows a messagebox error and does not change storage.
- Removing a blank email shows a messagebox error.
- Refresh failures should be shown in the existing status/log area or messagebox.
- Summary refresh should fail softly and keep the UI usable.

## Testing

Add controller tests with fake widgets and fake storage for:

- adding a suppression entry refreshes count/list
- invalid suppression email does not write
- removing a suppression entry refreshes count/list
- governance summary includes quota values and suppression count

Run:

```bash
python -m pytest -q tests/test_controllers.py
python -m pytest -q -rs
python -m compileall -q app license-platform/apps/api/app main.py
git diff --check
```

## Acceptance Criteria

- A user can see suppression count and current quota settings in the send area.
- A user can manually add and remove suppressed recipient emails from the desktop UI.
- Existing batch sending controls still work.
- Full test suite passes.
