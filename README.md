# GlobalReach PRO

GlobalReach PRO is a desktop workbench for B2B outreach email preparation and SMTP-based sending. It helps import lead lists, map contact fields, generate personalized outreach drafts, test SMTP accounts, and run controlled batch-send tasks.

## What It Does

- Imports CSV, XLSX, and XLS lead lists.
- Auto-maps common fields such as email, company, contact name, and product.
- Renders templates with variables such as `{Email}`, `{Name}`, `{Company}`, and `{Product}`.
- Generates outreach drafts with local variation logic, OpenAI-compatible APIs, or Gemini.
- Tests SMTP delivery and supports common provider presets.
- Sends batch emails through a saved SMTP account pool with account rotation.
- Supports attachments, per-email delay, retry on transient SMTP errors, stop control, duplicate-recipient policy, and send-result history.
- Includes an optional license-platform service for commercial/server-license deployments.

## What It Is Not

This project is not a full email marketing platform. It does not provide unsubscribe-link hosting, bounce processing, open/click tracking, complaint handling, or deliverability guarantees. Operators are responsible for lawful use, recipient consent, suppression lists, and compliance with applicable anti-spam and privacy rules.

## Project Layout

- `main.py` - desktop application entry point.
- `app/services/` - import, template, AI writing, SMTP, batch sending, preflight, and licensing services.
- `app/controllers/` - UI controller actions.
- `app/ui/` - CustomTkinter UI builders.
- `app/storage/` - SQLite storage code. Runtime database files are ignored and should not be committed.
- `tests/` - automated tests.
- `tools/` - desktop build and license integration helpers.
- `docs/` - design and deployment notes.
- `license-platform/` - optional FastAPI-based license server MVP.

## Maintainer Documents

- `CHANGELOG.md` - public release log.
- `MAINTENANCE.md` - maintenance tracks, verification commands, and release path.
- `RELEASE_HANDOFF.md` - current open-source handoff status and residual risks.
- `OPEN_SOURCE_CHECKLIST.md` - release readiness checklist.
- `SECURITY.md` - sensitive-data and responsible-use policy.

## Requirements

Desktop app:

- Python 3.11 or newer
- Tk support for Python
- `customtkinter`
- `darkdetect`
- `pandas`
- `openpyxl`

License platform:

- Python 3.11 or newer
- FastAPI stack listed in `license-platform/pyproject.toml`
- SQLite for local development or PostgreSQL for production-style deployments

## Local Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

If `import tkinter` fails, install or switch to a Python build that includes Tk. On macOS, a Homebrew Python build with Tk support usually works better than a broken copied virtual environment.

## Optional AI Configuration

The app can run without remote AI. In local mode it creates deterministic lead-specific variations.

For remote AI, configure these in the UI:

- Mode: `openai` or `gemini`
- Model
- API key
- Endpoint for OpenAI-compatible APIs
- Tone, offer summary, CTA, and signature

OpenAI-compatible endpoints must accept a `/v1/chat/completions` style request and return a `choices[0].message.content` response containing JSON with `subject` and `body`.

## Optional Licensing

Open-source desktop runs default to open-source mode when no server-license configuration is present.

Set these environment variables only when using the optional license platform:

```bash
GLOBALREACH_LICENSE_API_BASE_URL=https://license.example.com
GLOBALREACH_LICENSE_PRODUCT_CODE=globalreach_pro
```

Legacy local licensing is disabled by default because its algorithm is public in source releases. It can be enabled only for private backward compatibility:

```bash
GLOBALREACH_ENABLE_LEGACY_LOCAL_LICENSE=1
```

## Testing

Install the full development/test dependency set before running the full suite:

```bash
python -m pip install -r requirements-dev.txt
```

Core non-GUI tests:

```bash
python -m pytest tests/test_ai_writer.py tests/test_batch_sender.py tests/test_smtp_service.py tests/test_template.py tests/test_importer.py tests/test_license_service.py
```

Full test suite:

```bash
python -m pytest
```

The full suite includes Tk-based controller tests. If the active Python runtime cannot import `tkinter`, those controller tests are skipped; use a Python build with Tk support to exercise them locally.

## Packaging

Build helper:

```bash
python tools/build_desktop.py --target macos --backend pyinstaller --create-dmg
```

Generated artifacts under `dist/`, `build/`, `.nuitka-cache/`, and `.pyinstaller-cache/` are local outputs and are ignored by Git.

## Open-Source Release Notes

Before release tags or binary publication:

- Confirm GPL-3.0 remains the intended license for the public release.
- Do not commit `app/storage/*.db` or `license-platform/data/`.
- Do not commit SMTP credentials, AI API keys, license keys, activation tokens, customer data, lead lists, or send history.
- Review `OPEN_SOURCE_CHECKLIST.md`.
- Review `SECURITY.md`.

After publishing:

- Keep user-visible changes in `CHANGELOG.md`.
- Follow `MAINTENANCE.md` before release tags or binary builds.
- Keep `RELEASE_HANDOFF.md` updated when the publication status materially changes.

## License

This project is licensed under the GNU General Public License version 3. See `LICENSE` and `NOTICE`.
