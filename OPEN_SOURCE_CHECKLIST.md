# Open-Source Release Checklist

Use this checklist before pushing the repository to a public host.

## Blocking Items

- [x] Choose a license and add `LICENSE` (GPL-3.0-only).
- [ ] Confirm `.gitignore` excludes local databases, virtual environments, caches, and build artifacts.
- [ ] Remove local runtime databases from the publish set:
  - `app/storage/*.db`
  - `license-platform/data/`
- [ ] Confirm no `.env` files with real values are staged.
- [ ] Confirm no SMTP passwords, AI API keys, license keys, activation tokens, lead lists, customer data, or send history are staged.
- [ ] Run the core test command from `README.md`.
- [ ] Run full tests in an environment where `import tkinter` works.
- [ ] Decide whether `license-platform/` should be part of the first public release or split into a separate repository.

## Recommended Before First Public Release

- [ ] Add screenshots after checking they contain no customer or credential data.
- [ ] Add GitHub Actions or another CI workflow for core tests.
- [ ] Add a sample lead CSV with fake data.
- [ ] Add a contribution guide if outside contributors are expected.
- [ ] Replace local SQLite SMTP password storage with OS keychain/keyring support if distributing to non-technical users.
- [ ] Add suppression-list support before positioning this as a production outreach sender.

## License Decision

The selected public license is GPL-3.0-only. Before publishing binaries or installers, make sure the corresponding source for the released version is available under the same license terms.
