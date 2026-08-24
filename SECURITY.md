# Security Policy

## Supported versions

Security fixes are applied to the latest release on the default branch.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that may expose user data. Use GitHub Private Vulnerability Reporting for the repository, including the affected version, reproduction steps, impact, and any proposed mitigation.

## Data boundary

Codex Sync reads only its documented allowlist and writes to the private shared folder selected and controlled by each user. The project does not provide storage, does not share a developer-owned Store, and does not send synchronized content to the author.

The Store contains synchronized allowlisted files plus Codex Sync operational metadata: a random Store ID, random device IDs, user-chosen device names, timestamps, Plan IDs, and receipts. Device records and receipts must not contain synchronized file contents, but the entire Store should still be treated as private.

Credentials, `config.toml`, sessions, task history, databases, logs, caches, browser state, generated media, and other live Codex state remain outside the synchronization boundary. Optional memories require explicit opt-in. Reports must never include real credentials, private Codex data, session transcripts, memory contents, snapshot contents, or database files.

## Security model

- Plan IDs prevent a reviewed plan from being silently replaced before `sync --plan`.
- Store ID checks prevent accidental attachment to a different shared folder.
- Receipts verify that an expected shared-tree manifest is visible on the next Mac.
- Locks prevent overlapping writes on one mounted view; cloud-folder propagation can still be delayed, so devices must sync serially.
- Snapshots and pre-write backups support recovery but retain earlier synchronized content locally under `~/.codex-sync`; snapshots are not copied into the shared Store.

Store IDs, Plan IDs, and receipts are integrity and coordination identifiers, not passwords or proof against a malicious storage administrator. Codex Sync does not provide end-to-end encryption; users should choose a private transport whose access controls and encryption meet their needs.
