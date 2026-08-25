#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import os
import json
import importlib.util
from unittest import mock
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugins/codex-sync/skills/codex-sync/scripts/codex_sync.py"
)


def load_runtime():
    spec = importlib.util.spec_from_file_location("codex_sync_runtime", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CodexSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.shared = self.root / "transport" / "CodexSync"
        self.mini = self.root / "mac-mini"
        self.book = self.root / "macbook"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, home: Path, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--user-home", str(home), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result

    def write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def init_device(self, home: Path, name: str, *extra: str) -> None:
        self.run_cli(home, "init", "--store", str(self.shared), "--device", name, *extra)

    def reviewed_sync(
        self,
        home: Path,
        *,
        expected: int = 0,
        expect_receipt: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        status_args = ["status", "--json"]
        if expect_receipt:
            status_args.extend(["--expect", expect_receipt])
        status = self.run_cli(home, *status_args, expected=2 if expected == 2 else 0)
        plan_id = json.loads(status.stdout)["plan_id"]
        sync_args = ["sync", "--plan", plan_id]
        if expect_receipt:
            sync_args.extend(["--expect", expect_receipt])
        return self.run_cli(home, *sync_args, expected=expected)

    def quick_sync(
        self, home: Path, *, expected: int = 0
    ) -> subprocess.CompletedProcess[str]:
        return self.run_cli(home, "sync-now", expected=expected)

    def runtime_context(self):
        runtime = load_runtime()
        user_home = self.mini.resolve()
        layout = runtime.Layout(
            user_home=user_home,
            codex_home=user_home / ".codex",
            agents_home=user_home / ".agents",
            state_home=user_home / ".codex-sync",
        )
        config = runtime.load_config(layout)
        items, local_paths, shared_paths, state = runtime.plan_sync(layout, config)
        return runtime, layout, config, items, local_paths, shared_paths, state

    def create_device(self, home: Path, name: str, *extra: str) -> dict:
        self.run_cli(home, "create", "--store", str(self.shared), "--device", name, *extra)
        return json.loads((self.shared / "store.json").read_text(encoding="utf-8"))

    def receipt_from(self, result: subprocess.CompletedProcess[str]) -> str:
        line = next(line for line in result.stdout.splitlines() if line.startswith("Receipt: "))
        return line.split(": ", 1)[1]

    def restore_plan(self, home: Path, snapshot_id: str) -> str:
        preview = self.run_cli(home, "restore", "--id", snapshot_id, "--dry-run")
        line = next(
            line for line in preview.stdout.splitlines()
            if line.startswith("Restore Plan ID: ")
        )
        return line.split(": ", 1)[1]

    def fingerprint(self, root: Path) -> dict[str, tuple[int, int, bytes]]:
        if not root.exists():
            return {}
        return {
            path.relative_to(root).as_posix(): (
                path.stat().st_mode,
                path.stat().st_mtime_ns,
                path.read_bytes(),
            )
            for path in root.rglob("*")
            if path.is_file() and not path.is_symlink()
        }

    def test_create_join_store_identity_and_device_registry(self) -> None:
        metadata = self.create_device(self.mini, "mac-mini")
        config = json.loads(
            (self.mini / ".codex-sync/config.json").read_text(encoding="utf-8")
        )
        self.assertEqual("skills", config["sync_scope"])
        wrong = self.root / "wrong-transport/CodexSync"
        result = self.run_cli(
            self.book,
            "join", "--store", str(wrong), "--device", "macbook",
            "--expect-store-id", metadata["store_id"],
            expected=1,
        )
        self.assertIn("not initialized", result.stderr)
        self.assertFalse(wrong.exists())
        self.assertFalse((self.book / ".codex-sync/config.json").exists())

        self.run_cli(
            self.book,
            "join", "--store", str(self.shared), "--device", "macbook",
            "--expect-store-id", metadata["store_id"],
        )
        devices = json.loads(self.run_cli(self.book, "devices", "--json").stdout)["devices"]
        self.assertEqual({"mac-mini", "macbook"}, {item["name"] for item in devices})
        self.assertEqual(2, len({item["device_id"] for item in devices}))
        self.assertEqual({"skills"}, {item["sync_scope"] for item in devices})

    def test_join_rejects_wrong_store_id_without_local_writes(self) -> None:
        metadata = self.create_device(self.mini, "mac-mini")
        wrong_id = str(load_runtime().uuid.uuid4())
        self.assertNotEqual(metadata["store_id"], wrong_id)
        before = self.fingerprint(self.shared)
        result = self.run_cli(
            self.book,
            "join", "--store", str(self.shared), "--device", "macbook",
            "--expect-store-id", wrong_id,
            expected=1,
        )
        self.assertIn("Wrong shared store", result.stderr)
        self.assertEqual(before, self.fingerprint(self.shared))
        self.assertFalse((self.book / ".codex-sync/config.json").exists())

    def test_v01_configuration_upgrades_without_losing_data(self) -> None:
        self.write(self.mini / ".agents/skills/demo/SKILL.md", "legacy-data\n")
        self.write(
            self.shared / "store.json",
            json.dumps({"version": 1, "kind": "codex-sync", "created_at": "legacy"}),
        )
        (self.shared / "shared").mkdir(parents=True)
        self.write(
            self.mini / ".codex-sync/config.json",
            json.dumps({
                "version": 1,
                "store": str(self.shared.resolve()),
                "device": "legacy-mini",
                "include_memories": False,
            }),
        )
        result = self.reviewed_sync(self.mini)
        self.assertRegex(self.receipt_from(result), r"^[a-f0-9]{16}$")
        upgraded = json.loads((self.shared / "store.json").read_text(encoding="utf-8"))
        self.assertRegex(upgraded["store_id"], r"^[a-f0-9-]{36}$")
        local_config = json.loads(
            (self.mini / ".codex-sync/config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(upgraded["store_id"], local_config["store_id"])
        self.assertEqual("all", local_config["sync_scope"])
        self.assertEqual(
            "legacy-data\n",
            (self.shared / "shared/agents/skills/demo/SKILL.md").read_text(encoding="utf-8"),
        )
        upgraded["store_id"] = str(load_runtime().uuid.uuid4())
        (self.shared / "store.json").write_text(json.dumps(upgraded), encoding="utf-8")
        changed = self.run_cli(self.mini, "status", expected=1)
        self.assertIn("different Codex Sync store", changed.stderr)

    def test_plan_id_blocks_changed_plan_without_selected_file_writes(self) -> None:
        skill = self.mini / ".agents/skills/demo/SKILL.md"
        self.write(skill, "reviewed\n")
        self.create_device(self.mini, "mac-mini")
        status = json.loads(self.run_cli(self.mini, "status", "--json").stdout)
        self.write(skill, "changed-after-review\n")
        result = self.run_cli(
            self.mini, "sync", "--plan", status["plan_id"], expected=1
        )
        self.assertIn("Plan changed", result.stderr)
        self.assertFalse((self.shared / "shared/agents/skills/demo/SKILL.md").exists())
        self.assertFalse((self.mini / ".codex-sync/state.json").exists())
        self.assertFalse((self.shared / "receipts").exists())

    def test_plan_id_blocks_shared_change_after_review(self) -> None:
        skill = self.mini / ".agents/skills/demo/SKILL.md"
        self.write(skill, "baseline\n")
        self.create_device(self.mini, "mac-mini")
        self.reviewed_sync(self.mini)
        self.write(skill, "local-update\n")
        reviewed = json.loads(self.run_cli(self.mini, "status", "--json").stdout)
        shared_skill = self.shared / "shared/agents/skills/demo/SKILL.md"
        self.write(shared_skill, "late-shared-update\n")
        before_local = skill.read_bytes()
        before_shared = shared_skill.read_bytes()
        result = self.run_cli(
            self.mini, "sync", "--plan", reviewed["plan_id"], expected=1
        )
        self.assertIn("Plan changed", result.stderr)
        self.assertEqual(before_local, skill.read_bytes())
        self.assertEqual(before_shared, shared_skill.read_bytes())

    def test_status_json_is_stable_and_read_only(self) -> None:
        self.write(self.mini / ".codex/skills/demo/SKILL.md", "portable skill\n")
        metadata = self.create_device(self.mini, "mac-mini")
        before = self.fingerprint(self.root)
        first = self.run_cli(self.mini, "status", "--json")
        middle = self.fingerprint(self.root)
        second = self.run_cli(self.mini, "status", "--json")
        after = self.fingerprint(self.root)
        self.assertEqual(before, middle)
        self.assertEqual(middle, after)
        self.assertEqual(first.stdout, second.stdout)
        document = json.loads(first.stdout)
        self.assertEqual(metadata["store_id"], document["store"]["id"])
        self.assertEqual("skills", document["sync_scope"])
        self.assertEqual(1, document["counts"]["push"])
        self.assertEqual("upload_to_shared_folder", document["items"][0]["direction"])

    def test_receipt_handoff_requires_matching_files_and_integrity(self) -> None:
        skill = self.mini / ".agents/skills/demo/SKILL.md"
        self.write(skill, "from-mini\n")
        metadata = self.create_device(self.mini, "mac-mini")
        receipt = self.receipt_from(self.reviewed_sync(self.mini))
        self.run_cli(
            self.book,
            "join", "--store", str(self.shared), "--device", "macbook",
            "--expect-store-id", metadata["store_id"],
        )
        missing = self.run_cli(self.book, "status", "--expect", "0" * 16, expected=1)
        self.assertIn("has not arrived", missing.stderr)

        shared_skill = self.shared / "shared/agents/skills/demo/SKILL.md"
        original = shared_skill.read_text(encoding="utf-8")
        self.write(shared_skill, "receipt-arrived-before-file\n")
        mismatch = self.run_cli(self.book, "status", "--expect", receipt, expected=1)
        self.assertIn("matching shared files have not", mismatch.stderr)
        self.write(shared_skill, original)
        status = self.run_cli(self.book, "status", "--json", "--expect", receipt)
        approved = json.loads(status.stdout)
        self.assertEqual(receipt, approved["expected_receipt"])
        omitted = self.run_cli(
            self.book, "sync", "--plan", approved["plan_id"], expected=1
        )
        self.assertIn("Plan changed", omitted.stderr)
        self.reviewed_sync(self.book, expect_receipt=receipt)
        self.assertEqual("from-mini\n", (self.book / ".agents/skills/demo/SKILL.md").read_text(encoding="utf-8"))

        receipt_path = self.shared / "receipts" / f"{receipt}.json"
        tampered = json.loads(receipt_path.read_text(encoding="utf-8"))
        tampered["created_at"] = "changed"
        receipt_path.write_text(json.dumps(tampered), encoding="utf-8")
        invalid = self.run_cli(self.book, "status", "--expect", receipt, expected=1)
        self.assertIn("invalid or was changed", invalid.stderr)

    def test_snapshot_restore_and_tamper_rejection(self) -> None:
        skill = self.mini / ".agents/skills/demo/SKILL.md"
        self.write(skill, "version-one\n")
        self.create_device(self.mini, "mac-mini")
        snapshot = self.run_cli(self.mini, "snapshot")
        snapshot_id = snapshot.stdout.split("Snapshot ", 1)[1].split(":", 1)[0]
        self.write(skill, "version-two\n")
        restore_plan = self.restore_plan(self.mini, snapshot_id)
        self.assertEqual("version-two\n", skill.read_text(encoding="utf-8"))
        self.run_cli(self.mini, "restore", "--id", snapshot_id, "--plan", restore_plan)
        self.assertEqual("version-one\n", skill.read_text(encoding="utf-8"))
        history = json.loads(self.run_cli(self.mini, "history", "--json").stdout)["snapshots"]
        self.assertEqual(2, len(history))
        self.assertIn("before-restore", {entry["kind"] for entry in history})

        newest = self.run_cli(self.mini, "snapshot")
        newest_id = newest.stdout.split("Snapshot ", 1)[1].split(":", 1)[0]
        saved = self.mini / ".codex-sync/snapshots" / newest_id / "files/agents/skills/demo/SKILL.md"
        self.write(saved, "tampered\n")
        self.write(skill, "must-survive\n")
        rejected = self.run_cli(self.mini, "restore", "--id", newest_id, expected=1)
        self.assertIn("missing or changed", rejected.stderr)
        self.assertEqual("must-survive\n", skill.read_text(encoding="utf-8"))

    def test_restore_plan_blocks_late_edit_and_cross_store_snapshot(self) -> None:
        skill = self.mini / ".agents/skills/demo/SKILL.md"
        self.write(skill, "snapshot-content\n")
        self.create_device(self.mini, "mac-mini")
        created = self.run_cli(self.mini, "snapshot")
        snapshot_id = created.stdout.split("Snapshot ", 1)[1].split(":", 1)[0]
        self.write(skill, "reviewed-target\n")
        plan = self.restore_plan(self.mini, snapshot_id)
        self.write(skill, "late-edit\n")
        changed = self.run_cli(
            self.mini, "restore", "--id", snapshot_id, "--plan", plan, expected=1
        )
        self.assertIn("Restore plan changed", changed.stderr)
        self.assertEqual("late-edit\n", skill.read_text(encoding="utf-8"))

        second_store = self.root / "transport-two/CodexSync"
        self.run_cli(
            self.book, "create", "--store", str(second_store), "--device", "store-maker"
        )
        self.run_cli(self.mini, "configure", "--store", str(second_store))
        history = self.run_cli(self.mini, "history", "--json")
        self.assertIn(snapshot_id, history.stdout)
        wrong_store = self.run_cli(
            self.mini, "restore", "--id", snapshot_id, "--dry-run", expected=1
        )
        self.assertIn("different shared Store", wrong_store.stderr)

    def test_snapshot_history_survives_memory_selection_change_and_staging_debris(self) -> None:
        self.write(self.mini / ".codex/memories/MEMORY.md", "memory\n")
        self.create_device(self.mini, "mac-mini", "--include-memories")
        created = self.run_cli(self.mini, "snapshot")
        snapshot_id = created.stdout.split("Snapshot ", 1)[1].split(":", 1)[0]
        debris = self.mini / ".codex-sync/snapshots/.snapshot-interrupted"
        debris.mkdir()
        self.run_cli(self.mini, "configure", "--exclude-memories")
        history = self.run_cli(self.mini, "history", "--json")
        self.assertIn(snapshot_id, history.stdout)
        restore = self.run_cli(
            self.mini, "restore", "--id", snapshot_id, "--dry-run", expected=1
        )
        self.assertIn("not enabled", restore.stderr)

    def test_create_and_join_lock_failures_leave_no_local_configuration(self) -> None:
        self.shared.mkdir(parents=True)
        lock = self.shared / ".codex-sync.lock"
        lock.mkdir()
        self.write(lock / "owner.json", '{"device":"other","created_at":"now"}\n')
        create = self.run_cli(
            self.mini,
            "create", "--store", str(self.shared), "--device", "mini",
            expected=1,
        )
        self.assertIn("Shared store is locked", create.stderr)
        self.assertFalse((self.mini / ".codex-sync/config.json").exists())
        self.assertFalse((self.shared / "store.json").exists())

        (lock / "owner.json").unlink()
        lock.rmdir()
        metadata = self.create_device(self.mini, "mini")
        lock.mkdir()
        self.write(lock / "owner.json", '{"device":"other","created_at":"now"}\n')
        join = self.run_cli(
            self.book,
            "join", "--store", str(self.shared), "--device", "book",
            "--expect-store-id", metadata["store_id"],
            expected=1,
        )
        self.assertIn("Shared store is locked", join.stderr)
        self.assertFalse((self.book / ".codex-sync/config.json").exists())

    def test_two_device_updates_deletion_protection_and_conflict(self) -> None:
        mini_skill = self.mini / ".agents/skills/demo/SKILL.md"
        self.write(mini_skill, "mini-v1\n")
        self.init_device(self.mini, "mac-mini")
        self.run_cli(self.mini, "doctor")
        self.reviewed_sync(self.mini)

        shared_skill = self.shared / "shared/agents/skills/demo/SKILL.md"
        self.assertEqual("mini-v1\n", shared_skill.read_text(encoding="utf-8"))

        self.init_device(self.book, "macbook")
        self.reviewed_sync(self.book)
        book_skill = self.book / ".agents/skills/demo/SKILL.md"
        self.assertEqual("mini-v1\n", book_skill.read_text(encoding="utf-8"))

        self.write(mini_skill, "mini-v2\n")
        self.reviewed_sync(self.mini)
        self.reviewed_sync(self.book)
        self.assertEqual("mini-v2\n", book_skill.read_text(encoding="utf-8"))

        book_skill.unlink()
        self.reviewed_sync(self.book)
        self.assertEqual("mini-v2\n", book_skill.read_text(encoding="utf-8"))

        self.write(book_skill, "book-edit\n")
        self.write(shared_skill, "shared-edit\n")
        self.run_cli(self.book, "status", expected=2)
        self.reviewed_sync(self.book, expected=2)
        self.assertEqual("book-edit\n", book_skill.read_text(encoding="utf-8"))
        self.assertEqual("shared-edit\n", shared_skill.read_text(encoding="utf-8"))
        conflicts = list((self.book / ".codex-sync/conflicts").rglob("SKILL.md.local"))
        self.assertEqual(1, len(conflicts))

        self.run_cli(
            self.book,
            "resolve", "--path", "agents/skills/demo/SKILL.md", "--prefer", "local",
        )
        self.assertEqual("book-edit\n", shared_skill.read_text(encoding="utf-8"))
        self.run_cli(self.book, "status")
        result = self.run_cli(
            self.book,
            "resolve", "--path", "agents/skills/demo/SKILL.md", "--prefer", "local",
            expected=1,
        )
        self.assertIn("not currently conflicted", result.stderr)

    def test_sync_now_handles_three_step_handoffs_without_manual_ids(self) -> None:
        mini_skill = self.mini / ".agents/skills/mini/SKILL.md"
        self.write(mini_skill, "from-mini\n")
        metadata = self.create_device(self.mini, "mac-mini")
        first = self.quick_sync(self.mini)
        self.assertIn("Automatic receipt: first sync", first.stdout)
        self.assertIn("Quick sync complete", first.stdout)

        self.run_cli(
            self.book,
            "join", "--store", str(self.shared), "--device", "windows-pc",
            "--expect-store-id", metadata["store_id"],
        )
        second = self.quick_sync(self.book)
        self.assertIn("Automatic receipt:", second.stdout)
        self.assertIn("from mac-mini", second.stdout)
        self.assertEqual(
            "from-mini\n",
            (self.book / ".agents/skills/mini/SKILL.md").read_text(encoding="utf-8"),
        )

        book_skill = self.book / ".codex/skills/windows/SKILL.md"
        self.write(book_skill, "from-windows\n")
        third = self.quick_sync(self.book)
        self.assertIn("Latest Store activity is already from this device", third.stdout)
        fourth = self.quick_sync(self.mini)
        self.assertIn("from windows-pc", fourth.stdout)
        self.assertEqual(
            "from-windows\n",
            (self.mini / ".codex/skills/windows/SKILL.md").read_text(encoding="utf-8"),
        )

    def test_sync_now_stops_before_writes_when_same_skill_conflicts(self) -> None:
        mini_skill = self.mini / ".agents/skills/demo/SKILL.md"
        self.write(mini_skill, "baseline\n")
        metadata = self.create_device(self.mini, "mac-mini")
        self.quick_sync(self.mini)
        self.run_cli(
            self.book,
            "join", "--store", str(self.shared), "--device", "windows-pc",
            "--expect-store-id", metadata["store_id"],
        )
        self.quick_sync(self.book)

        book_skill = self.book / ".agents/skills/demo/SKILL.md"
        self.write(book_skill, "windows-edit\n")
        self.write(mini_skill, "mac-edit\n")
        self.quick_sync(self.mini)
        shared_skill = self.shared / "shared/agents/skills/demo/SKILL.md"
        receipts_before = sorted((self.shared / "receipts").glob("*.json"))
        state_before = (self.book / ".codex-sync/state.json").read_bytes()

        result = self.quick_sync(self.book, expected=2)
        self.assertIn("Quick sync stopped before changing selected files", result.stderr)
        self.assertIn("CONFLICT agents/skills/demo/SKILL.md", result.stderr)
        self.assertEqual("windows-edit\n", book_skill.read_text(encoding="utf-8"))
        self.assertEqual("mac-edit\n", shared_skill.read_text(encoding="utf-8"))
        self.assertEqual(state_before, (self.book / ".codex-sync/state.json").read_bytes())
        self.assertEqual(receipts_before, sorted((self.shared / "receipts").glob("*.json")))

    def test_exclusions_and_memories_opt_in(self) -> None:
        self.write(self.mini / ".codex/AGENTS.md", "rules\n")
        self.write(self.mini / ".codex/rules/default.rules", "allow\n")
        self.write(self.mini / ".codex/skills/custom/SKILL.md", "custom\n")
        self.write(self.mini / ".codex/skills/codex-sync/SKILL.md", "tool instructions\n")
        self.write(
            self.mini / ".codex/skills/codex-sync/scripts/codex_sync.py",
            "print('tool runtime')\n",
        )
        self.write(self.mini / ".codex/skills/.system/private.txt", "excluded\n")
        self.write(
            self.mini / ".codex/skills/.codex-sync-backup-test/SKILL.md",
            "installer backup\n",
        )
        self.write(
            self.mini / ".codex/skills/.codex-sync-install.test/SKILL.md",
            "installer staging\n",
        )
        self.write(self.mini / ".codex/skills/custom/auth.json", "excluded\n")
        self.write(self.mini / ".codex/skills/custom/.env", "PASSWORD=excluded-value\n")
        self.write(self.mini / ".codex/skills/custom/.npmrc", "token=excluded-value\n")
        self.write(self.mini / ".codex/skills/custom/credentials.json", "excluded\n")
        self.write(self.mini / ".codex/skills/custom/id_rsa", "excluded\n")
        self.write(self.mini / ".codex/skills/custom/notes.txt", "token=excluded-value\n")
        self.write(self.mini / ".codex/memories/MEMORY.md", "memory\n")
        self.write(self.mini / ".codex/memories/memories_1.sqlite", "database\n")
        self.init_device(self.mini, "mac-mini")
        self.reviewed_sync(self.mini)

        shared_root = self.shared / "shared"
        self.assertFalse((shared_root / "codex/AGENTS.md").exists())
        self.assertFalse((shared_root / "codex/rules/default.rules").exists())
        self.assertTrue((shared_root / "codex/skills/custom/SKILL.md").exists())
        self.assertFalse((shared_root / "codex/skills/codex-sync/SKILL.md").exists())
        self.assertFalse(
            (shared_root / "codex/skills/codex-sync/scripts/codex_sync.py").exists()
        )
        self.assertFalse((shared_root / "codex/skills/.system/private.txt").exists())
        self.assertFalse(
            (shared_root / "codex/skills/.codex-sync-backup-test/SKILL.md").exists()
        )
        self.assertFalse(
            (shared_root / "codex/skills/.codex-sync-install.test/SKILL.md").exists()
        )
        self.assertFalse((shared_root / "codex/skills/custom/auth.json").exists())
        self.assertFalse((shared_root / "codex/skills/custom/.env").exists())
        self.assertFalse((shared_root / "codex/skills/custom/.npmrc").exists())
        self.assertFalse((shared_root / "codex/skills/custom/credentials.json").exists())
        self.assertFalse((shared_root / "codex/skills/custom/id_rsa").exists())
        self.assertFalse((shared_root / "codex/skills/custom/notes.txt").exists())
        self.assertFalse((shared_root / "codex/memories/MEMORY.md").exists())

        self.run_cli(self.mini, "configure", "--include-memories")
        self.reviewed_sync(self.mini)
        self.assertTrue((shared_root / "codex/memories/MEMORY.md").exists())
        self.assertFalse((shared_root / "codex/memories/memories_1.sqlite").exists())
        if os.name != "nt":
            self.assertEqual(0o700, self.shared.stat().st_mode & 0o777)
            self.assertEqual(0o700, (self.mini / ".codex-sync").stat().st_mode & 0o777)

    def test_skills_scope_excludes_device_rules_on_push_and_pull(self) -> None:
        self.write(self.mini / ".codex/skills/local/SKILL.md", "local skill\n")
        self.write(self.mini / ".codex/rules/default.rules", "local rule\n")
        self.write(self.mini / ".codex/AGENTS.md", "local agents\n")
        metadata = self.create_device(self.mini, "mac-mini")
        first = self.reviewed_sync(self.mini)

        shared_root = self.shared / "shared"
        self.assertTrue((shared_root / "codex/skills/local/SKILL.md").exists())
        self.assertFalse((shared_root / "codex/rules/default.rules").exists())
        self.assertFalse((shared_root / "codex/AGENTS.md").exists())

        self.write(shared_root / "codex/skills/remote/SKILL.md", "remote skill\n")
        self.write(shared_root / "codex/rules/remote.rules", "remote rule\n")
        self.write(shared_root / "codex/AGENTS.md", "remote agents\n")
        self.run_cli(
            self.book,
            "join", "--store", str(self.shared), "--device", "macbook",
            "--expect-store-id", metadata["store_id"],
        )
        self.reviewed_sync(self.book)

        self.assertTrue((self.book / ".codex/skills/remote/SKILL.md").exists())
        self.assertFalse((self.book / ".codex/rules/remote.rules").exists())
        self.assertFalse((self.book / ".codex/AGENTS.md").exists())
        self.assertRegex(self.receipt_from(first), r"^[a-f0-9]{16}$")

    def test_all_scope_preserves_legacy_rules_and_agents_behavior(self) -> None:
        self.write(self.mini / ".codex/skills/demo/SKILL.md", "skill\n")
        self.write(self.mini / ".codex/rules/default.rules", "rule\n")
        self.write(self.mini / ".codex/AGENTS.md", "agents\n")
        metadata = self.create_device(self.mini, "mac-mini", "--scope", "all")
        receipt = self.receipt_from(self.reviewed_sync(self.mini))

        shared_root = self.shared / "shared"
        self.assertTrue((shared_root / "codex/skills/demo/SKILL.md").exists())
        self.assertTrue((shared_root / "codex/rules/default.rules").exists())
        self.assertTrue((shared_root / "codex/AGENTS.md").exists())

        self.run_cli(
            self.book,
            "join", "--store", str(self.shared), "--device", "macbook",
            "--expect-store-id", metadata["store_id"], "--scope", "all",
        )
        self.reviewed_sync(self.book, expect_receipt=receipt)
        self.assertEqual(
            "rule\n",
            (self.book / ".codex/rules/default.rules").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            "agents\n",
            (self.book / ".codex/AGENTS.md").read_text(encoding="utf-8"),
        )

    def test_scope_change_is_non_destructive_and_changes_plan_identity(self) -> None:
        self.write(self.mini / ".codex/skills/demo/SKILL.md", "skill\n")
        self.write(self.mini / ".codex/rules/default.rules", "rule\n")
        self.write(self.mini / ".codex/AGENTS.md", "agents\n")
        self.create_device(self.mini, "mac-mini", "--scope", "all")
        self.reviewed_sync(self.mini)
        all_plan = json.loads(self.run_cli(self.mini, "status", "--json").stdout)

        self.run_cli(self.mini, "configure", "--scope", "skills")
        skills_plan = json.loads(self.run_cli(self.mini, "status", "--json").stdout)
        self.assertNotEqual(all_plan["plan_id"], skills_plan["plan_id"])
        self.assertEqual("skills", skills_plan["sync_scope"])
        self.assertTrue((self.mini / ".codex/rules/default.rules").exists())
        self.assertTrue((self.mini / ".codex/AGENTS.md").exists())
        self.assertTrue((self.shared / "shared/codex/rules/default.rules").exists())
        self.assertTrue((self.shared / "shared/codex/AGENTS.md").exists())

    def test_receipt_rejects_different_sync_scope(self) -> None:
        self.write(self.mini / ".codex/skills/demo/SKILL.md", "skill\n")
        metadata = self.create_device(self.mini, "mac-mini", "--scope", "all")
        receipt = self.receipt_from(self.reviewed_sync(self.mini))
        self.run_cli(
            self.book,
            "join", "--store", str(self.shared), "--device", "macbook",
            "--expect-store-id", metadata["store_id"],
        )
        result = self.run_cli(
            self.book, "status", "--expect", receipt, expected=1
        )
        self.assertIn("different sync scope", result.stderr)

    def test_secret_detection_covers_single_file_root_and_full_file(self) -> None:
        self.write(self.mini / ".codex/AGENTS.md", "token=1234567890abcdef\n")
        late_secret = self.mini / ".agents/skills/demo/late-secret.txt"
        self.write(late_secret, ("x" * (1024 * 1024 + 16)) + "\ntoken=1234567890abcdef\n")
        self.init_device(self.mini, "mac-mini")
        status = self.run_cli(self.mini, "status")
        self.assertIn("push=0", status.stdout)
        self.reviewed_sync(self.mini)
        self.assertFalse((self.shared / "shared/codex/AGENTS.md").exists())
        self.assertFalse((self.shared / "shared/agents/skills/demo/late-secret.txt").exists())

    def test_secret_detection_covers_provider_tokens_and_nested_structured_fields(self) -> None:
        selected = self.mini / ".codex/skills/custom"
        self.write(
            selected / "nested.json",
            json.dumps({"providers": {"openai": {"apiKey": "abcdefghijklmnop"}}}),
        )
        self.write(
            selected / "nested.yaml",
            "providers:\n  openai:\n    api_key: abcdefghijklmnop\n"
            "flow: {provider: {access_token: qrstuvwxyzabcdef}}\n",
        )
        self.write(
            selected / "provider-tokens.txt",
            "\n".join([
                "openai=sk-proj-" + "a" * 30,
                "github=github_pat_" + "b" * 30,
                "gitlab=glpat-" + "c" * 30,
                "slack=xoxb-" + "d" * 30,
                "huggingface=hf_" + "e" * 30,
                "google=AIza" + "f" * 30,
                "jwt=eyJ" + "g" * 20 + "." + "h" * 20 + "." + "i" * 20,
            ]),
        )
        self.write(
            selected / "ordinary-doc.md",
            "Set api_key to YOUR_API_KEY in the environment; never commit tokens.\n",
        )
        self.init_device(self.mini, "mac-mini")
        status = self.run_cli(self.mini, "status")
        self.assertIn("push=1", status.stdout)
        self.reviewed_sync(self.mini)

        shared = self.shared / "shared/codex/skills/custom"
        for name in ("nested.json", "nested.yaml", "provider-tokens.txt"):
            self.assertFalse((shared / name).exists())
        self.assertTrue((shared / "ordinary-doc.md").exists())

    def test_shared_relative_paths_reject_windows_forms(self) -> None:
        runtime = load_runtime()
        config = {"sync_scope": "skills", "include_memories": False}
        layout = runtime.Layout(
            user_home=self.mini,
            codex_home=self.mini / ".codex",
            agents_home=self.mini / ".agents",
            state_home=self.mini / ".codex-sync",
        )
        self.assertTrue(runtime.rel_is_safe("agents/skills/demo/SKILL.md", config))
        unsafe_paths = (
            r"agents\skills\demo\SKILL.md",
            r"\agents\skills\demo\SKILL.md",
            r"\\server\share\agents\skills\demo\SKILL.md",
            "//server/share/agents/skills/demo/SKILL.md",
            "C:/agents/skills/demo/SKILL.md",
            r"C:\agents\skills\demo\SKILL.md",
            "agents/skills/demo/\x00SKILL.md",
        )
        for rel in unsafe_paths:
            with self.subTest(rel=rel):
                self.assertFalse(runtime.rel_is_safe(rel, config))
                with self.assertRaises(runtime.SyncError):
                    runtime.target_for(rel, layout, config)

    def test_unsafe_store_is_rejected(self) -> None:
        result = self.run_cli(
            self.mini,
            "init", "--store", str(self.mini / ".codex/sync"), "--device", "mini",
            expected=1,
        )
        self.assertIn("overlaps protected path", result.stderr)

    def test_shared_lock_blocks_writes_and_can_be_cleared(self) -> None:
        skill = self.mini / ".agents/skills/demo/SKILL.md"
        self.write(skill, "content\n")
        self.init_device(self.mini, "mac-mini")
        lock = self.shared / ".codex-sync.lock"
        lock.mkdir()
        self.write(lock / "owner.json", '{"device":"macbook","created_at":"now"}\n')
        result = self.reviewed_sync(self.mini, expected=1)
        self.assertIn("Shared store is locked", result.stderr)
        self.assertFalse((self.shared / "shared/agents/skills/demo/SKILL.md").exists())
        self.run_cli(self.mini, "unlock", expected=1)
        self.assertTrue(lock.exists())
        self.run_cli(self.mini, "unlock", "--force")
        self.assertFalse(lock.exists())
        self.reviewed_sync(self.mini)
        self.assertTrue((self.shared / "shared/agents/skills/demo/SKILL.md").exists())

    @unittest.skipIf(os.name == "nt", "creating symlinks may require Windows Developer Mode")
    def test_shared_lock_symlink_is_rejected_without_reading_target(self) -> None:
        skill = self.mini / ".agents/skills/demo/SKILL.md"
        self.write(skill, "content\n")
        self.create_device(self.mini, "mac-mini")
        plan = json.loads(self.run_cli(self.mini, "status", "--json").stdout)["plan_id"]
        outside = self.root / "outside-lock"
        outside.mkdir()
        self.write(outside / "owner.json", '{"device":"attacker"}\n')
        (self.shared / ".codex-sync.lock").symlink_to(outside, target_is_directory=True)
        result = self.run_cli(self.mini, "sync", "--plan", plan, expected=1)
        self.assertIn("lock path is unsafe", result.stderr)
        self.assertFalse((self.shared / "shared/agents/skills/demo/SKILL.md").exists())

    def test_explicit_user_home_ignores_codex_home_environment(self) -> None:
        selected = self.mini / ".codex/skills/selected/SKILL.md"
        wrong = self.root / "wrong-codex/skills/wrong/SKILL.md"
        self.write(selected, "selected\n")
        self.write(wrong, "wrong\n")
        env = dict(os.environ)
        env["CODEX_HOME"] = str(self.root / "wrong-codex")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--user-home", str(self.mini),
             "init", "--store", str(self.shared), "--device", "mini"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        status = subprocess.run(
            [sys.executable, str(SCRIPT), "--user-home", str(self.mini), "status", "--json"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False,
        )
        self.assertEqual(0, status.returncode, status.stdout + status.stderr)
        plan_id = json.loads(status.stdout)["plan_id"]
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--user-home", str(self.mini),
             "sync", "--plan", plan_id],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue((self.shared / "shared/codex/skills/selected/SKILL.md").exists())
        self.assertFalse((self.shared / "shared/codex/skills/wrong/SKILL.md").exists())

    @unittest.skipIf(os.name == "nt", "creating symlinks may require Windows Developer Mode")
    def test_atomic_copy_rejects_source_replaced_by_symlink(self) -> None:
        runtime = load_runtime()
        source_root = self.root / "source"
        destination_root = self.root / "destination"
        source = source_root / "safe.txt"
        secret = self.root / "outside-secret.txt"
        destination = destination_root / "safe.txt"
        self.write(source, "safe\n")
        self.write(secret, "secret\n")
        expected_hash = runtime.hash_file(source)
        source.unlink()
        source.symlink_to(secret)
        destination_root.mkdir()
        with self.assertRaises(runtime.SyncError):
            runtime.atomic_copy(
                source,
                destination,
                destination_root,
                source_root,
                expected_hash,
                None,
            )
        self.assertFalse(destination.exists())

    def test_atomic_copy_rejects_destination_changed_after_comparison(self) -> None:
        runtime = load_runtime()
        source_root = self.root / "source"
        destination_root = self.root / "destination"
        source = source_root / "file.txt"
        destination = destination_root / "file.txt"
        self.write(source, "shared-v2\n")
        self.write(destination, "local-v1\n")
        expected_source_hash = runtime.hash_file(source)
        expected_destination_hash = runtime.hash_file(destination)
        self.write(destination, "local-late-edit\n")
        with self.assertRaises(runtime.SyncError):
            runtime.atomic_copy(
                source,
                destination,
                destination_root,
                source_root,
                expected_source_hash,
                expected_destination_hash,
            )
        self.assertEqual("local-late-edit\n", destination.read_text(encoding="utf-8"))

    def test_pull_rejects_destination_changed_after_backup(self) -> None:
        local = self.mini / ".agents/skills/demo/SKILL.md"
        self.write(local, "baseline\n")
        self.init_device(self.mini, "mini")
        self.reviewed_sync(self.mini)
        shared = self.shared / "shared/agents/skills/demo/SKILL.md"
        self.write(shared, "shared-v2\n")
        runtime, layout, config, items, local_paths, shared_paths, state = self.runtime_context()
        original_backup = runtime.backup_copy

        def backup_then_edit(*args, **kwargs):
            result = original_backup(*args, **kwargs)
            if args[4] == "before-pull":
                self.write(local, "local-late-edit\n")
            return result

        with mock.patch.object(runtime, "backup_copy", side_effect=backup_then_edit):
            with self.assertRaises(runtime.SyncError) as raised:
                runtime.execute_sync(
                    layout, config, Path(config["store"]) / "shared", items, local_paths, shared_paths, state
                )
        self.assertIn("Destination changed after comparison", str(raised.exception))
        self.assertEqual("local-late-edit\n", local.read_text(encoding="utf-8"))

    def test_push_rejects_destination_changed_after_backup(self) -> None:
        local = self.mini / ".agents/skills/demo/SKILL.md"
        self.write(local, "baseline\n")
        self.init_device(self.mini, "mini")
        self.reviewed_sync(self.mini)
        shared = self.shared / "shared/agents/skills/demo/SKILL.md"
        self.write(local, "local-v2\n")
        runtime, layout, config, items, local_paths, shared_paths, state = self.runtime_context()
        original_backup = runtime.backup_copy

        def backup_then_edit(*args, **kwargs):
            result = original_backup(*args, **kwargs)
            if args[4] == "before-push":
                self.write(shared, "shared-late-edit\n")
            return result

        with mock.patch.object(runtime, "backup_copy", side_effect=backup_then_edit):
            with self.assertRaises(runtime.SyncError) as raised:
                runtime.execute_sync(
                    layout, config, Path(config["store"]) / "shared", items, local_paths, shared_paths, state
                )
        self.assertIn("Destination changed after comparison", str(raised.exception))
        self.assertEqual("shared-late-edit\n", shared.read_text(encoding="utf-8"))

    def test_resolve_rejects_destination_changed_after_backups(self) -> None:
        local = self.mini / ".agents/skills/demo/SKILL.md"
        self.write(local, "baseline\n")
        self.init_device(self.mini, "mini")
        self.reviewed_sync(self.mini)
        shared = self.shared / "shared/agents/skills/demo/SKILL.md"
        self.write(local, "local-v2\n")
        self.write(shared, "shared-v2\n")
        runtime, layout, config, items, local_paths, shared_paths, state = self.runtime_context()
        item = next(candidate for candidate in items if candidate.action == "conflict")
        original_backup = runtime.backup_copy
        calls = 0

        def backup_then_edit(*args, **kwargs):
            nonlocal calls
            result = original_backup(*args, **kwargs)
            calls += 1
            if calls == 2:
                self.write(shared, "shared-late-edit\n")
            return result

        args = type("Args", (), {"prefer": "local"})()
        with mock.patch.object(runtime, "backup_copy", side_effect=backup_then_edit):
            with self.assertRaises(runtime.SyncError) as raised:
                runtime.execute_resolve(
                    args,
                    layout,
                    config,
                    item,
                    state,
                    Path(config["store"]) / "shared",
                    local_paths[item.rel],
                    shared_paths[item.rel],
                )
        self.assertIn("Destination changed after comparison", str(raised.exception))
        self.assertEqual("shared-late-edit\n", shared.read_text(encoding="utf-8"))

    def test_resolve_conflict_when_one_side_is_missing(self) -> None:
        skill = self.mini / ".agents/skills/demo/SKILL.md"
        self.write(skill, "baseline\n")
        self.init_device(self.mini, "mini")
        self.reviewed_sync(self.mini)
        shared = self.shared / "shared/agents/skills/demo/SKILL.md"
        skill.unlink()
        self.write(shared, "shared-change\n")
        self.run_cli(self.mini, "status", expected=2)
        self.run_cli(
            self.mini,
            "resolve", "--path", "agents/skills/demo/SKILL.md", "--prefer", "shared",
        )
        self.assertEqual("shared-change\n", skill.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
