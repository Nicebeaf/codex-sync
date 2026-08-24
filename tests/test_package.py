#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE = ROOT / ".agents/plugins/marketplace.json"
INSTALLER = ROOT / "install.sh"
WINDOWS_INSTALLER = ROOT / "install.ps1"


class PackageTest(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX installer is tested on macOS")
    def test_standalone_installer_is_idempotent_in_clean_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            home.mkdir()
            environment = dict(os.environ)
            environment["HOME"] = str(home)
            environment.pop("CODEX_HOME", None)

            for attempt in range(2):
                result = subprocess.run(
                    ["/bin/sh", str(INSTALLER)],
                    cwd=ROOT,
                    env=environment,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(
                    0,
                    result.returncode,
                    f"attempt {attempt + 1}:\n{result.stdout}{result.stderr}",
                )

                skills = home / ".codex/skills"
                installed = skills / "codex-sync"
                self.assertTrue((installed / "SKILL.md").is_file())
                self.assertTrue((installed / "scripts/codex_sync.py").is_file())
                self.assertEqual([installed], list(skills.iterdir()))
                self.assertFalse((installed / "codex-sync").exists())

                help_result = subprocess.run(
                    [sys.executable, str(installed / "scripts/codex_sync.py"), "--help"],
                    env=environment,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(
                    0,
                    help_result.returncode,
                    help_result.stdout + help_result.stderr,
                )
                self.assertIn("init", help_result.stdout)
                self.assertIn("create", help_result.stdout)
                self.assertIn("join", help_result.stdout)
                self.assertIn("sync", help_result.stdout)
                self.assertIn("sync-now", help_result.stdout)

    @unittest.skipUnless(os.name == "nt", "PowerShell installer is tested on Windows")
    def test_windows_installer_is_idempotent_in_clean_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            home.mkdir()
            environment = dict(os.environ)
            environment["HOME"] = str(home)
            environment["USERPROFILE"] = str(home)
            environment["CODEX_HOME"] = str(home / ".codex")

            for attempt in range(2):
                result = subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-ExecutionPolicy", "Bypass",
                        "-File", str(WINDOWS_INSTALLER),
                    ],
                    cwd=ROOT,
                    env=environment,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(
                    0,
                    result.returncode,
                    f"attempt {attempt + 1}:\n{result.stdout}{result.stderr}",
                )

                skills = home / ".codex/skills"
                installed = skills / "codex-sync"
                self.assertTrue((installed / "SKILL.md").is_file())
                self.assertTrue((installed / "scripts/codex_sync.py").is_file())
                self.assertEqual([installed], list(skills.iterdir()))

                help_result = subprocess.run(
                    [sys.executable, str(installed / "scripts/codex_sync.py"), "--help"],
                    env=environment,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(
                    0,
                    help_result.returncode,
                    help_result.stdout + help_result.stderr,
                )
                self.assertIn("sync-now", help_result.stdout)

    def test_marketplace_plugin_installs_into_clean_cache(self) -> None:
        catalog = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
        self.assertEqual("codex-sync", catalog["name"])
        entry = catalog["plugins"][0]
        self.assertEqual("codex-sync", entry["name"])
        self.assertEqual("AVAILABLE", entry["policy"]["installation"])

        source = entry["source"]["path"]
        self.assertTrue(source.startswith("./"))
        self.assertNotIn("..", Path(source).parts)
        plugin = (ROOT / source[2:]).resolve()
        plugin.relative_to(ROOT.resolve())
        self.assertTrue(plugin.is_dir())

        manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(entry["name"], manifest["name"])
        self.assertEqual("0.4.0", manifest["version"])

        with tempfile.TemporaryDirectory() as temporary:
            installed = Path(temporary) / "cache/codex-sync/local"
            shutil.copytree(plugin, installed)
            skills = installed / manifest["skills"]
            self.assertTrue((skills / "codex-sync/SKILL.md").is_file())
            runtime = skills / "codex-sync/scripts/codex_sync.py"
            result = subprocess.run(
                [sys.executable, str(runtime), "--help"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("init", result.stdout)
            self.assertIn("sync", result.stdout)
            self.assertIn("sync-now", result.stdout)

    def test_release_contains_no_local_paths_or_secret_shapes(self) -> None:
        forbidden_names = {"auth.json", "config.toml", "history.jsonl"}
        secret_patterns = [
            re.compile(r"/Users/[^/\s]+/(?:Desktop|Documents|Downloads)/"),
            re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
            re.compile(r"ghp_[A-Za-z0-9]{20,}"),
            re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        ]
        text_suffixes = {
            ".md", ".json", ".py", ".sh", ".ps1", ".yml", ".yaml", ".txt"
        }
        for path in ROOT.rglob("*"):
            self.assertFalse(path.is_symlink(), f"symlink not allowed in release: {path}")
            if path.is_file() and path.name in forbidden_names:
                self.fail(f"forbidden state file in release: {path}")
            if not path.is_file() or path.suffix.lower() not in text_suffixes:
                continue
            text = path.read_text(encoding="utf-8")
            for pattern in secret_patterns:
                self.assertIsNone(pattern.search(text), f"sensitive pattern in {path}: {pattern.pattern}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
