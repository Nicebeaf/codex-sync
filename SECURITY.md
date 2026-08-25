# Security Policy

Codex Sync is an independent, community-maintained project. It is not an official OpenAI product, service, or repository, and it is not affiliated with, sponsored by, or endorsed by OpenAI.

## Supported versions

Security fixes are applied to the latest release on the default branch.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that may expose user data. Use GitHub Private Vulnerability Reporting for the repository, including the affected version, reproduction steps, impact, and any proposed mitigation.

## Data boundary

Codex Sync reads only its documented allowlist and writes to the private Store selected and controlled by each user. The project does not provide storage, does not share a developer-owned Store, and does not send synchronized content to the author.

The Store contains synchronized allowlisted files plus Codex Sync operational metadata: a random Store ID, random device IDs, user-chosen device names, timestamps, Plan IDs, and receipts. Device records and receipts must not contain synchronized file contents, but the entire Store should still be treated as private.

Credentials, `config.toml`, sessions, task history, databases, logs, caches, browser state, generated media, and other live Codex state remain outside the synchronization boundary. Optional memories require explicit opt-in. Reports must never include real credentials, private Codex data, session transcripts, memory contents, snapshot contents, or database files.

The installed `codex-sync` Skill and its `.codex-sync-*` installer staging or backup directories are also outside the Store. The running synchronization tool must be installed and updated independently on each device; otherwise secret-shape filtering or version skew could produce a partial runtime copy.

## Security model

- Plan IDs prevent a reviewed plan from being silently replaced before `sync --plan`.
- Store ID checks prevent accidental attachment to a different shared folder.
- Receipts verify that an expected shared-tree manifest is visible on the next Mac.
- Locks prevent overlapping writes on one mounted view; cloud-folder propagation can still be delayed, so devices must sync serially.
- Snapshots and pre-write backups support recovery but retain earlier synchronized content locally under `~/.codex-sync`; snapshots are not copied into the shared Store.

Store IDs, Plan IDs, and receipts are integrity and coordination identifiers, not passwords or proof against a malicious storage administrator. Codex Sync does not provide end-to-end encryption; users should choose a private transport whose access controls and encryption meet their needs. Filename and content filters for credentials and secret-shaped data are best-effort defense-in-depth checks, not an absolute guarantee that every secret will be detected or excluded.

## Dependency installation boundary

Dependency readiness is local to the current device. It is not written into the shared Store, synchronization state, or receipts. `deps status`, `deps plan`, and `deps verify` are read-only. `deps install` requires the exact current dependency Plan ID and rechecks that plan before starting a package manager.

Synchronized Skills cannot provide shell commands, URLs, package names, environment variables, or install scripts. A Skill may only reference logical IDs from the dependency catalog bundled with the reviewed Codex Sync release. Codex Sync may also report common Python imports found by static AST inspection, but it never executes `SKILL.md` text or imported Skill code to discover dependencies. Unknown imports and Skills without `dependencies.json` remain unmanaged rather than being guessed.

Supported installers use argument vectors with `shell=False`. Python and npm packages are requested from their public registries with package identifiers fixed in the built-in catalog; npm lifecycle scripts are disabled. Homebrew formulas and WinGet IDs are also fixed in that catalog. These constraints reduce command-injection and registry-configuration risk, but package installation still executes third-party software and may require platform permissions or license acceptance. Review every displayed command and its affected Skills before approving the Plan ID.

Package-manager changes are not transactional and cannot be rolled back by Codex Sync snapshots. After every supported installation, the built-in probe must pass; this confirms the declared module, command, runtime, or application is visible, not that every workflow in the Skill has completed an end-to-end functional test.
