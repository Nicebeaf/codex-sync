# Contributing

Contributions are welcome through focused issues and pull requests.

Unless a pull request or patch states otherwise in writing, contributions are
submitted for distribution under this repository's MIT License. Contributors
must have the right to submit the work under those terms.

1. Keep the synchronization allowlist narrow.
2. Never add credential, session, database, log, cache, browser, or device-state paths.
3. Preserve conflict refusal, pre-write backups, non-propagating deletions, path-containment checks, and symlink refusal.
4. Preserve v0.2 coordination guarantees: Store identity checks, reviewed Plan IDs, receipt verification, device-registry validation, and recoverable snapshots.
5. Keep public examples on the safe flow: `create`, `status` or `status --json`, `sync --plan` and its printed receipt, `join --expect-store-id`, `devices`, `snapshot`, `history`, and `restore`.
6. Add an observable test for every behavior change. Test mismatched IDs, stale plans, missing or tampered receipts, interrupted writes, snapshot verification, and restore rollback where relevant.
7. Run `python3 tests/test_codex_sync.py` and `python3 tests/test_package.py` before opening a pull request.

Changes that broaden synchronized data must explain the privacy and corruption risks and remain opt-in.

Fixtures and bug reports must use generated Store IDs, device IDs, receipts, paths, and content. Never commit real credentials, personal data, a real shared Store, device registry, snapshot, receipt, user path, or synchronized Codex file. Use synthetic content even when a real example would be easier to reproduce.
