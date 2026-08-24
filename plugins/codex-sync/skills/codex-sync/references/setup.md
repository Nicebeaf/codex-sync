# Setup and operating model

`codex-sync` does not upload data itself. Its Store must be a private folder that both computers already receive through iCloud Drive, OneDrive, Dropbox, Syncthing, a NAS mount, or another user-controlled transport. Every user creates their own Store; no synchronized content is shared with the project author.

## Recommended macOS and Windows setup

1. Choose a new or empty private folder visible at an absolute path on both computers. For a Mac-to-Windows pair, OneDrive, Dropbox, Syncthing, or a NAS is usually simpler than an OS-specific path alias.
2. Run `create --scope skills` on the first computer with a unique device name. Save the printed Store ID.
3. Run `doctor`, then `status --json` or human-readable `status`. Review the exact Plan ID before `sync --plan`.
4. Save the receipt printed by a successful sync.
5. Wait until the private transport has fully propagated to the second computer.
6. Run `join --scope skills` on the second computer with a different device name and `--expect-store-id` set to the first computer's Store ID.
7. Run `devices`, `doctor`, and `status --json --expect <RECEIPT>`. Review initial conflicts before applying the new Plan ID.
8. For later handoffs, run `sync-now` on only one computer at a time. It discovers the latest receipt automatically.

The Store can be any absolute path. `icloud` is a macOS-only shortcut; `onedrive` uses the configured OneDrive environment path when available:

```bash
python3 scripts/codex_sync.py create --store icloud --device mac-mini --scope skills
```

```powershell
py scripts\codex_sync.py create --store onedrive --device windows-pc --scope skills
```

The first setup prints a UUID-shaped Store ID. On the other computer:

```bash
python3 scripts/codex_sync.py join \
  --store icloud \
  --device computer-b \
  --expect-store-id "<STORE_ID>" \
  --scope skills
```

Store ID verifies folder identity; it is not a secret. A receipt verifies a specific completed shared-tree manifest and should be copied exactly:

```bash
python3 scripts/codex_sync.py status --json --expect "<RECEIPT>"
python3 scripts/codex_sync.py sync --plan "<PLAN_ID>" --expect "<RECEIPT>"
```

## Commands

- `create`: create a new Store, initialize its identity, and configure the first device.
- `join`: configure another device for an existing Store; use `--expect-store-id` to prevent joining the wrong folder.
- `configure`: change the store, device name, `skills|all` scope, or Memories opt-in without discarding comparison state unless the store changes.
- `doctor`: verify configuration, path separation, access, and selected roots.
- `status`: compute actions without changing files; `--json` exposes the full plan and Plan ID for agent use.
- `sync --plan`: apply only the reviewed Plan ID, back up overwritten files, preserve conflicts, and update comparison state.
- `sync-now`: automatically verify the newest successful handoff and apply one conflict-free plan; conflicts stop before selected files change.
- A successful `sync --plan` prints the handoff receipt for the next device.
- `devices`: list registered devices and their recent Store activity without reading synchronized file contents.
- `snapshot`: create a restorable local snapshot.
- `history`: list recoverable local snapshots; `--json` provides structured output.
- `restore`: preview or restore one snapshot while preserving the current state first.
- `resolve`: copy one chosen conflict side over the other after preserving both.
- `unlock`: inspect a shared lock; `unlock --force` removes a stale lock only after the user confirms no sync is active.

## Plan and receipt rules

- Human-readable `status` and `status --json` describe the same plan. Use JSON when Codex must extract the Plan ID.
- A Plan ID is valid only for the exact local, shared, and baseline hashes reviewed by `status`.
- Re-run `status` after any conflict resolution, restore, manual edit, or receipt mismatch.
- Never bypass `--expect` because a cloud folder appears present in Finder; receipt mismatch means the expected manifest is not yet visible.
- The Store lock protects one mounted view. Receipt verification handles handoffs, but joined computers must still avoid simultaneous sync.
- Receipts bind the `skills|all` scope. Both devices must select the same scope for a handoff.

## Scope and 0.2 migration

New configurations default to `skills`, selecting only `~/.agents/skills` and `~/.codex/skills`. Device-level `~/.codex/rules` and `~/.codex/AGENTS.md` are selected only by `--scope all`.

Configurations created by 0.2 retain `all` so upgrading does not silently change an existing setup. After both computers update to 0.4, switch each one to Skills-only sharing with:

```bash
python3 scripts/codex_sync.py configure --scope skills
```

This changes selection only. It does not delete files from either computer or the Store.

## Snapshot recovery

Inspect history and preview a restore before applying it:

```bash
python3 scripts/codex_sync.py snapshot
python3 scripts/codex_sync.py history
python3 scripts/codex_sync.py restore --id "<SNAPSHOT_ID>" --dry-run
python3 scripts/codex_sync.py restore --id "<SNAPSHOT_ID>" --plan "<RESTORE_PLAN_ID>"
```

Snapshots stay on the current device under `~/.codex-sync/snapshots`; they are not copied to the Store. Apply only the Restore Plan ID printed by the dry run. Restore does not require the shared folder to be available. Do not edit snapshot manifests, device records, Store metadata, or receipts by hand.

## What is deliberately not synchronized

Codex sessions and app databases are live state and can be damaged by file-level synchronization. Use Codex Remote or Handoff when the same task must move between computers. Authentication must be completed separately on each computer.

`config.toml` is excluded because it may contain credentials, machine-specific paths, MCP endpoints, and permission settings. Known credential filenames and common secret-shaped contents are also excluded, but this is not a substitute for reviewing `status`. Put portable project configuration in a repository's `.codex/config.toml`; keep secrets in environment variables or the system keychain.

The Store does contain Codex Sync metadata: a random Store ID, random device IDs, user-chosen device names, timestamps, Plan IDs, and receipts. Keep that metadata in the same private folder; it is operational state, not data sent to the author.
