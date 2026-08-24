# Codex Sync

[简体中文](README.zh-CN.md)

Codex Sync is an open-source Codex plugin for safely sharing user-authored Skills between Macs. It uses a private folder that **you** choose and control, such as iCloud Drive, Dropbox, Syncthing, or a NAS mount.

Codex Sync does not provide a cloud service, shared account, or author-operated storage. Every person uses their own private shared folder; no synchronized content is sent to the author.

## Requirements

- macOS
- Python 3.9 or newer
- A private folder synchronized between the Macs
- A Codex version with plugin support; tested with Codex CLI `0.149.0-alpha.4.1`

If `codex plugin --help` is unavailable, install the standalone Skill instead.

## What it synchronizes

New configurations default to the `skills` scope, which shares only:

- `~/.agents/skills`
- `~/.codex/skills`, excluding `.system`

`~/.codex/rules` and `~/.codex/AGENTS.md` are device-level configuration. They are excluded by default and cannot be replaced by another Mac unless `--scope all` is selected explicitly.

Local Memories can be enabled explicitly. Known credential filenames, secret-shaped content, sessions, history, databases, logs, plugins, caches, browser state, generated images, automations, device identifiers, and symlinks are excluded. Users must still inspect `status` and must not store credentials inside Skill folders.

## Safety properties

- Three-way comparison distinguishes local changes, shared changes, and concurrent edits.
- Skills use a two-way union: a Skill added on either Mac enters the shared set, while deletions do not propagate.
- `status` produces a reviewable plan ID; `sync --plan` refuses to apply a different plan.
- A stable store ID prevents a Mac from silently joining the wrong shared folder.
- Receipts bind a successful handoff to the shared-tree manifest, so another Mac can verify that the expected cloud-folder update is visible.
- Conflicting files are preserved on both sides and never overwritten automatically.
- Existing files are backed up before replacement.
- Snapshot history and restore make recovery an explicit, verifiable operation.
- Deletions do not propagate.
- A shared-store lock prevents overlapping writes on directly mounted storage.
- Sync should still run serially when the transport is a cloud folder because cloud propagation may be delayed.
- Each file is limited to 20 MiB; one side is limited to 10,000 files and 512 MiB per run.

## Install as a plugin

After this repository is published:

```bash
codex plugin marketplace add Nicebeaf/codex-sync
```

Open the Plugins directory in the ChatGPT desktop app, select the **Codex Sync** marketplace, install **Codex Sync**, and start a new chat. In Codex CLI, run `/plugins`, install it, then start a new session.

GitHub marketplace distribution makes the plugin publicly installable but does not automatically list it in the universal Plugins Directory. Universal listing requires the separate [plugin submission process](https://developers.openai.com/plugins/deploy/submission).

To test a local clone before publishing:

```bash
git clone https://github.com/Nicebeaf/codex-sync.git
codex plugin marketplace add ./codex-sync
```

## Install only the standalone Skill

Run the repository installer. It copies the standalone Skill to `~/.codex/skills/codex-sync`, so the installed copy survives removal of the clone:

```bash
sh install.sh
```

Restart Codex if `$codex-sync` does not appear immediately.

## Safe two-Mac workflow

Ask Codex to use this Skill, or run the bundled script directly. The examples below use shell variables only to make the handoff values clear.

### 1. Create the store on the first Mac

`create` only accepts a new or empty private folder. Save the printed `STORE_ID`; the second Mac uses it to verify that it is joining the intended store.

```bash
SYNC=plugins/codex-sync/skills/codex-sync/scripts/codex_sync.py
python3 "$SYNC" create --store icloud --device mac-mini --scope skills
python3 "$SYNC" doctor
```

### 2. Review an exact plan, then sync

Use human output when reviewing in a terminal, or JSON when Codex or another program needs the complete plan. `sync` requires the reviewed plan ID; if anything changes after review, it stops instead of applying a new plan.

```bash
python3 "$SYNC" status
python3 "$SYNC" status --json
python3 "$SYNC" sync --plan "<PLAN_ID>"
```

A successful `sync` prints a `RECEIPT`. Save it: the receipt represents the completed shared-tree manifest, not just a timestamp.

### 3. Join from the second Mac

Wait for the private transport to finish, then join with the exact store ID. Use a different device name and require the first Mac's receipt during review and sync.

```bash
SYNC=plugins/codex-sync/skills/codex-sync/scripts/codex_sync.py
python3 "$SYNC" join \
  --store icloud \
  --device macbook \
  --expect-store-id "<STORE_ID>" \
  --scope skills
python3 "$SYNC" doctor
python3 "$SYNC" devices
python3 "$SYNC" status --json --expect "<RECEIPT>"
python3 "$SYNC" sync --plan "<PLAN_ID>" --expect "<RECEIPT>"
```

The second successful `sync` prints the receipt for the next handoff.

Repeat the receipt handoff whenever work moves from one Mac to the other. A receipt proves that the expected manifest is visible; it does not make delayed cloud transports safe for simultaneous sync.

### Migrate an existing 0.2 configuration to Skills-only sharing

Configurations created by 0.2 retain the legacy `all` scope so an upgrade never changes behavior silently. After updating both Macs to 0.3, run this once on **each Mac**:

```bash
python3 "$SYNC" configure --scope skills
```

Changing scope only changes future selection. It does not delete existing rules, `AGENTS.md`, or Skills from either the Mac or the shared Store. Both Macs must use the same scope for the next handoff; receipts reject a mismatched scope.

GitHub/Marketplace is the installation and update source for the Codex Sync Skill. Your private Store is what shares your own Skills between Macs.

### 4. Inspect and restore snapshots

```bash
python3 "$SYNC" snapshot
python3 "$SYNC" history
python3 "$SYNC" restore --id "<SNAPSHOT_ID>" --dry-run
python3 "$SYNC" restore --id "<SNAPSHOT_ID>" --plan "<RESTORE_PLAN_ID>"
```

Snapshots stay on this Mac under `~/.codex-sync/snapshots`; they are not copied into the shared Store. The dry run prints a Restore Plan ID, and the actual restore refuses any later target change. A restore also preserves the current local state before replacing it and does not require the shared folder to be available.

## Command model

- `create --scope skills`: create a new shared store that defaults to Skills-only sharing.
- `join --expect-store-id --scope skills`: join an existing store only if its identity and scope match.
- `configure --scope skills|all`: switch between Skills-only and legacy full scope without deleting files.
- `status` / `status --json`: inspect the current plan without writing.
- `sync --plan`: apply only the exact reviewed plan.
- A successful `sync --plan` prints the handoff receipt for the next Mac.
- `devices`: inspect the store's registered Codex Sync devices.
- `snapshot` / `history` / `restore`: save, inspect, and recover local synchronized state.
- `resolve`: choose one side of a confirmed conflict after both versions are preserved.

## Positioning among related tools

As of August 2026, several useful projects solve adjacent problems. Codex Sync deliberately stays narrower: two-way Skills sharing through the user's private transport, with safety checks for plans, store identity, cloud handoff, conflicts, and recovery.

| Project | Public focus | How Codex Sync differs |
| --- | --- | --- |
| [skills-manager](https://github.com/xingkongliang/skills-manager) | Desktop library, broad agent support, private Git backup, and multi-device Skills sync | Codex Sync is not a library or GUI; it defaults to Codex Skills only, while rules and `AGENTS.md` require the explicit `all` scope. |
| [skillshare](https://github.com/runkids/skillshare) | One source for Skills and other resources across many AI tools, with Git workflows and auditing | Codex Sync focuses on two-way Codex state through an existing private transport and refuses unreviewed plans. |
| [skills-hub](https://github.com/qufei1993/skills-hub) | Desktop installation, organization, updating, and deployment of Skills to many tools | Codex Sync focuses on cross-computer safety and recovery, not discovery or bulk Skill management. |
| [vsync](https://github.com/nicepkg/vsync) | One-way, cross-tool configuration conversion from a chosen source | Codex Sync handles edits made on multiple computers and preserves conflicts instead of treating one tool as authoritative. |
| [ai-config-sync-manager](https://github.com/slash9494/ai-config-sync-manager) | Claude Code ↔ Codex configuration translation on one computer | Codex Sync does not translate host formats; it verifies private handoffs between computers. |

This comparison describes public positioning, not a claim that one project is universally better. Choose a general Skill manager or cross-tool converter when that is the primary need.

## Development

Requirements: macOS and Python 3.9 or newer. The runtime uses only the Python standard library.

```bash
python3 -m py_compile plugins/codex-sync/skills/codex-sync/scripts/codex_sync.py
python3 tests/test_codex_sync.py
python3 tests/test_package.py
```

## Publish your fork

```bash
git init
git add .
git commit -m "Initial open-source release"
gh repo create codex-sync --public --source . --remote origin --push
```

Review the repository contents before publishing. Do not add real Codex data, shared-store contents, `auth.json`, `config.toml`, sessions, databases, or local backup folders.

## Security and privacy

See [SECURITY.md](SECURITY.md). The project is distributed under the [MIT License](LICENSE).

## Official documentation

- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Build plugins](https://developers.openai.com/plugins/build/plugins)
