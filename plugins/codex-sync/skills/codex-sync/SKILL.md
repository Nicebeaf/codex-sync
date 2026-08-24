---
name: codex-sync
description: Safely share user-authored Codex Skills between Macs as a two-way union through the user's own private shared folder, with reviewed plans, store identity, handoff receipts, snapshots, and conflict preservation. Device rules and AGENTS.md are excluded by default. Never copy credentials, sessions, logs, caches, or databases.
---

# Codex Sync

Use `scripts/codex_sync.py` for every operation. Version 0.3 defaults to the `skills` scope, shares Skills as a two-way union, binds writes to a reviewed plan, identifies each store and device, verifies cross-Mac handoffs with receipts, keeps snapshot history, and retains three-way comparison, locks, backups, conflict refusal, and no deletion propagation.

The user supplies and controls the transport. Codex Sync does not provide storage, does not use a folder owned by the author, and does not send synchronized content to the author.

## Create the first Mac

1. Read [references/setup.md](references/setup.md).
2. Ask only for the private shared-folder location if it cannot be inferred. Prefer a folder already synchronized by iCloud Drive, Dropbox, Syncthing, a NAS, or another user-controlled service.
3. Create a new Store with a distinct device name. Never reuse a non-empty unrelated directory:

```bash
python3 scripts/codex_sync.py create --store "/absolute/private/CodexSync" --device "mac-mini" --scope skills
```

Record the printed Store ID. Add `--include-memories` only after the user accepts that memories are generated state and Codex must not run simultaneously on both Macs during sync.

Run `doctor`, then obtain a reviewable plan. Prefer JSON when operating as an agent; summarize its `push`, `pull`, `conflict`, and `same` counts for the user.

```bash
python3 scripts/codex_sync.py doctor
python3 scripts/codex_sync.py status --json
python3 scripts/codex_sync.py sync --plan "<PLAN_ID>"
```

Do not run `sync` until the user has approved the current plan. If the plan ID changes, show the new plan and ask again. A successful sync prints the receipt for the next Mac.

## Join another Mac

Wait for the private transport to finish, then require the Store ID printed by `create`:

```bash
python3 scripts/codex_sync.py join \
  --store "/absolute/private/CodexSync" \
  --device "macbook" \
  --expect-store-id "<STORE_ID>" \
  --scope skills
python3 scripts/codex_sync.py devices
```

Require the previous Mac's latest receipt during the next review and write. A missing or mismatched receipt means the expected shared-tree manifest is not visible; stop rather than bypassing the check.

```bash
python3 scripts/codex_sync.py status --json --expect "<RECEIPT>"
python3 scripts/codex_sync.py sync --plan "<PLAN_ID>" --expect "<RECEIPT>"
```

## Routine use

Run `doctor`, then `status --json` or the human-readable `status`. Show the planned `push`, `pull`, `conflict`, and `same` counts before any write. Apply only the displayed Plan ID.

```bash
python3 scripts/codex_sync.py doctor
python3 scripts/codex_sync.py status --json
python3 scripts/codex_sync.py sync --plan "<PLAN_ID>"
```

Use `devices` to inspect registered devices. When changing Macs, pass the prior receipt with `--expect`; never treat the shared lock as protection against delayed cloud propagation.

## Snapshot recovery

List history before restoring. Preview the selected restore, explain which paths change, and apply it only after approval.

```bash
python3 scripts/codex_sync.py snapshot
python3 scripts/codex_sync.py history
python3 scripts/codex_sync.py restore --id "<SNAPSHOT_ID>" --dry-run
python3 scripts/codex_sync.py restore --id "<SNAPSHOT_ID>" --plan "<RESTORE_PLAN_ID>"
```

Snapshots stay on this Mac under `~/.codex-sync/snapshots`; they are not stored in the shared Store. Apply only the Restore Plan ID printed by the dry run; if it changes, show the new preview and ask again. A restore preserves the current local state first and does not require the shared folder to be available. Never edit snapshot or receipt files manually.

## Conflict handling

Never choose a side silently. A normal `sync` stores both versions under `~/.codex-sync/conflicts/` and leaves the originals unchanged. After the user chooses, resolve exactly one path:

```bash
python3 scripts/codex_sync.py resolve --path "agents/skills/example/SKILL.md" --prefer local
python3 scripts/codex_sync.py resolve --path "agents/skills/example/SKILL.md" --prefer shared
```

Run `status --json` again after resolution and apply its new Plan ID. Do not reuse the plan from before resolution.

If a killed process leaves a lock, inspect it with `unlock`. Use `unlock --force` only after confirming neither Mac is syncing.

## Safety boundary

- Allowed by default in `skills` scope: `~/.agents/skills` and `~/.codex/skills` except `.system`.
- Device configuration is excluded by default: `~/.codex/rules` and `~/.codex/AGENTS.md` are selected only with explicit `--scope all` or `configure --scope all`.
- Configurations created by 0.2 retain `all` for compatibility. To adopt Skills-only sharing, update both Macs and run `configure --scope skills` on each one. Scope changes never delete files, and receipt verification rejects different scopes.
- Optional: `~/.codex/memories`, enabled only during `create --include-memories`, `join --include-memories`, or `configure --include-memories`.
- Excluded: known credential filenames and secret-shaped content, `auth.json`, `config.toml`, sessions, archived sessions, task history, SQLite/WAL/SHM files, logs, plugins, caches, generated images, Computer Use/browser state, temporary files, automations, Codex runtime device state, and symlinks. Still inspect `status`; never store credentials inside Skill folders.
- Store metadata includes Codex Sync's random Store ID, random device IDs, device names, timestamps, plan identifiers, and receipts. It does not include file contents in device records, but it still belongs only in the user's private shared folder.
- Limits: 20 MiB per file, 10,000 files and 512 MiB per side per run.
- Do not point the shared store at `~/.codex`, `~/.agents`, a filesystem root, or either selected source directory.
- Do not run sync concurrently on both Macs. The lock protects a directly mounted Store, while receipt verification protects a specific handoff; neither turns delayed cloud transport into a concurrent database.
- Stop after one failed attempt and report the exact error; do not weaken safety checks.
