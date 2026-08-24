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
GITIGNORE = ROOT / ".gitignore"
README = ROOT / "README.md"
README_ZH = ROOT / "README.zh-CN.md"
WORKFLOW = ROOT / ".github/workflows/test.yml"
DEPENDABOT = ROOT / ".github/dependabot.yml"


class PackageTest(unittest.TestCase):
    def _gitignore_matches(self, path: str) -> bool:
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", "--", path],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertIn(
            result.returncode,
            (0, 1),
            f"git check-ignore failed for {path}: {result.stderr}",
        )
        return result.returncode == 0

    def test_documentation_declares_project_and_privacy_boundary(self) -> None:
        english = README.read_text(encoding="utf-8")
        chinese = README_ZH.read_text(encoding="utf-8")
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

        self.assertIn("independent, community-maintained project", english)
        self.assertIn("not an official OpenAI product", english)
        self.assertIn("private `Store`", english)
        self.assertIn("does **not** provide end-to-end encryption", english)
        self.assertIn("not an absolute guarantee", english)

        self.assertIn("独立维护的社区项目", chinese)
        self.assertIn("不是 OpenAI 官方产品", chinese)
        self.assertIn("私有 `Store`", chinese)
        self.assertIn("不提供端到端加密", chinese)
        self.assertIn("不能绝对保证", chinese)

        self.assertIn("independent, community-maintained project", security)
        self.assertIn("does not provide end-to-end encryption", security)
        self.assertIn("not an absolute guarantee", security)

    def test_gitignore_blocks_local_secret_and_state_paths(self) -> None:
        self.assertTrue(GITIGNORE.is_file())
        for path in (
            ".env",
            ".env.local",
            ".ssh/id_ed25519",
            "private-key.pem",
            "credentials.json",
            "auth.json",
            "history.jsonl",
            "local.sqlite3",
            "debug.log",
            "secrets/token.txt",
            ".codex-sync/store.json",
        ):
            with self.subTest(path=path):
                self.assertTrue(self._gitignore_matches(path))

    def test_gitignore_keeps_repository_configuration_trackable(self) -> None:
        for path in (
            ".env.example",
            ".env.sample",
            ".env.template",
            "config.toml",
            ".github/workflows/test.yml",
            ".agents/plugins/marketplace.json",
            "plugins/codex-sync/.codex-plugin/plugin.json",
            "plugins/codex-sync/skills/codex-sync/agents/openai.yaml",
        ):
            with self.subTest(path=path):
                self.assertFalse(self._gitignore_matches(path))

    def test_workflow_uses_pinned_current_actions_and_deterministic_safety_check(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(
            workflow,
            r"actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\b",
        )
        self.assertRegex(
            workflow,
            r"actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97\b",
        )
        self.assertNotRegex(workflow, r"actions/(?:checkout|setup-python)@v\d")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("name: Reproducible source safety check", workflow)
        self.assertIn("test_release_contains_no_local_paths_or_secret_shapes", workflow)

    def test_dependabot_tracks_github_actions_updates(self) -> None:
        configuration = DEPENDABOT.read_text(encoding="utf-8")
        self.assertIn("package-ecosystem: github-actions", configuration)
        self.assertIn("interval: weekly", configuration)
        self.assertIn("open-pull-requests-limit: 5", configuration)

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
