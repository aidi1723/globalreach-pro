# Open-Source Release Checklist

Use this checklist before pushing the repository to a public host and before cutting public release tags.

## Blocking Items

- [x] Choose a license and add `LICENSE` (GPL-3.0-only).
- [x] Confirm `.gitignore` excludes local databases, virtual environments, caches, and build artifacts.
- [x] Remove local runtime databases from the publish set:
  - `app/storage/*.db`
  - `license-platform/data/`
- [x] Confirm no `.env` files with real values are staged.
- [x] Confirm no SMTP passwords, AI API keys, license keys, activation tokens, lead lists, customer data, or send history are staged.
- [x] Run the core test command from `README.md`.
- [x] Run full tests in an environment where `import tkinter` works.
- [x] Decide whether `license-platform/` should be part of the first public release or split into a separate repository.

Decision: `license-platform/` is included in the first public release as an optional MVP server-license component.

## Recommended Post-Release Improvements

- [ ] Add screenshots after checking they contain no customer or credential data.
- [x] Add GitHub Actions or another CI workflow for core tests.
- [ ] Add a sample lead CSV with fake data.
- [ ] Add a contribution guide if outside contributors are expected.
- [ ] Replace local SQLite SMTP password storage with OS keychain/keyring support if distributing to non-technical users.
- [x] Add service/storage suppression-list support before positioning this as a controlled production outreach sender.
- [ ] Add a desktop suppression-list management screen before broad non-technical distribution.

## License Decision

The selected public license is GPL-3.0-only. Before publishing binaries or installers, make sure the corresponding source for the released version is available under the same license terms.
