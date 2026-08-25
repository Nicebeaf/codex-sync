# Changelog

All notable changes to Codex Sync are documented here.

## [0.5.0] - Unreleased

### Added

- Dependency-readiness workflow for synchronized Skills: `deps status`, reviewed `deps plan`, exact-plan `deps install`, and probe-only `deps verify`.
- Strict, catalog-backed `dependencies.json` authoring documentation and migration guidance.
- Dependency scanning across user `~/.agents/skills` and `~/.codex/skills`, with static recognition of common Python imports.

### Safety and verification boundary

- Installation is limited to reviewed, controlled `pip`, `npm`, `brew`, or `winget` argv on the current device; it does not write the Store or receipts.
- The Codex Sync runtime itself and standalone installer staging/backup directories under the Skills roots are excluded from synchronization; install the tool independently on each device.
- Legacy Skills without a manifest remain `legacy_unmanaged`; unknown imports, malformed manifests, unsupported platforms, and manual dependencies remain partial or blocked.
- `deps verify` checks declared and inferred dependency probes only. It is not a complete Skill business-workflow test.
- Package-manager installation is non-transactional and can require system permissions or package-source/EULA acceptance.

## [0.4.0] - 2026-08-25

### Added

- Skills-only sharing by default for `~/.agents/skills` and user-authored `~/.codex/skills`.
- macOS and Windows support, including standalone shell and PowerShell installers.
- `sync-now` for the routine three-step handoff without copied Plan IDs or receipts.
- Cross-platform CI on Python 3.9 and 3.12.
- Weekly Dependabot checks for pinned GitHub Actions.

### Safety

- Conflict-free quick sync stops before selected files change when a conflict exists.
- Expanded detection for common provider tokens, JWTs, and nested JSON/YAML secret fields.
- Rejection of Windows drive, UNC, backslash, NUL, and control-character shared paths.
- GitHub Actions are pinned to full commit SHAs and run with read-only repository permissions.
- Documentation now states the private Store, encryption, secret-filter, and independent-community-project boundaries explicitly.

### Compatibility

- Existing 0.2 configurations retain the legacy `all` scope until users explicitly run `configure --scope skills` on each computer.
- Scope changes do not delete local or shared files.
