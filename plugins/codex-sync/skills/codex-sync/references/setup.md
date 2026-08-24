# Setup and operating model

`codex-sync` does not upload data itself. Its Store must be a private folder that both Macs already receive through iCloud Drive, Dropbox, Syncthing, a NAS mount, or another user-controlled transport. Every user creates their own Store; no synchronized content is shared with the project author.

## Recommended two-Mac setup

1. Choose a new or empty private folder such as `~/Library/Mobile Documents/com~apple~CloudDocs/CodexSync` on the Mac mini.
2. Run `create --scope skills` on the Mac mini with device name `mac-mini`. Save the printed Store ID.
3. Run `doctor`, then `status --json` or human-readable `status`. Review the exact Plan ID before `sync --plan`.
4. Save the receipt printed by a successful sync.
5. Wait until the private transport has fully propagated to the MacBook.
6. Run `join --scope skills` on the MacBook with device name `macbook` and `--expect-store-id` set to the first Mac's Store ID.
7. Run `devices`, `doctor`, and `status --json --expect <RECEIPT>`. Review initial conflicts before applying the new Plan ID.
8. Run sync on only one Mac at a time. Carry the latest receipt to the next Mac on every handoff.

The store can be any absolute path. The literal value `icloud` resolves to the current user's standard iCloud Drive location:

```bash
python3 scripts/codex_sync.py create --store icloud --device mac-mini --scope skills
```

The first setup prints a UUID-shaped Store ID. On the other Mac:

```bash
python3 scripts/codex_sync.py join \
  --store icloud \
  --device macbook \
  --expect-store-id "<STORE_ID>" \
  --scope skills
```

Store ID verifies folder identity; it is not a secret. A receipt verifies a specific completed shared-tree manifest and should be copied exactly:

```bash
python3 scripts/codex_sync.py status --json --expect "<RECEIPT>"
python3 scripts/codex_sync.py sync --plan "<PLAN_ID>" --expect "<RECEIPT>"
```

## Commands

- `create`: create a new Store, initialize its identity, and configure the first Mac.
- `join`: configure another Mac for an existing Store; use `--expect-store-id` to prevent joining the wrong folder.
- `configure`: change the store, device name, `skills|all` scope, or Memories opt-in without discarding comparison state unless the store changes.
- `doctor`: verify configuration, path separation, access, and selected roots.
- `status`: compute actions without changing files; `--json` exposes the full plan and Plan ID for agent use.
- `sync --plan`: apply only the reviewed Plan ID, back up overwritten files, preserve conflicts, and update comparison state.
- A successful `sync --plan` prints the handoff receipt for the next Mac.
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
- The Store lock protects one mounted view. Receipt verification handles handoffs, but both Macs must still avoid simultaneous sync.
- Receipts bind the `skills|all` scope. Both Macs must select the same scope for a handoff.

## Scope and 0.2 migration

New configurations default to `skills`, selecting only `~/.agents/skills` and `~/.codex/skills`. Device-level `~/.codex/rules` and `~/.codex/AGENTS.md` are selected only by `--scope all`.

Configurations created by 0.2 retain `all` so upgrading does not silently change an existing setup. After both Macs update to 0.3, switch each one to Skills-only sharing with:

```bash
python3 scripts/codex_sync.py configure --scope skills
```

This changes selection only. It does not delete files from either Mac or the Store.

## Snapshot recovery

Inspect history and preview a restore before applying it:

```bash
python3 scripts/codex_sync.py snapshot
python3 scripts/codex_sync.py history
python3 scripts/codex_sync.py restore --id "<SNAPSHOT_ID>" --dry-run
python3 scripts/codex_sync.py restore --id "<SNAPSHOT_ID>" --plan "<RESTORE_PLAN_ID>"
```

Snapshots stay on this Mac under `~/.codex-sync/snapshots`; they are not copied to the Store. Apply only the Restore Plan ID printed by the dry run. Restore does not require the shared folder to be available. Do not edit snapshot manifests, device records, Store metadata, or receipts by hand.

## What is deliberately not synchronized

Codex sessions and app databases are live state and can be damaged by file-level synchronization. Use Codex Remote or Handoff when the same task must move between computers. Authentication must be completed separately on each Mac.

`config.toml` is excluded because it may contain credentials, machine-specific paths, MCP endpoints, and permission settings. Known credential filenames and common secret-shaped contents are also excluded, but this is not a substitute for reviewing `status`. Put portable project configuration in a repository's `.codex/config.toml`; keep secrets in environment variables or the system keychain.

The Store does contain Codex Sync metadata: a random Store ID, random device IDs, user-chosen device names, timestamps, Plan IDs, and receipts. Keep that metadata in the same private folder; it is operational state, not data sent to the author.
