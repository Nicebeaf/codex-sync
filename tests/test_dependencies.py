#!/usr/bin/env python3
"""Unit tests for Codex Sync's local Skill dependency readiness subsystem."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugins/codex-sync/skills/codex-sync/scripts/codex_sync.py"
)


def load_runtime():
    """Load an isolated runtime module so mocks cannot leak between tests."""
    name = f"codex_sync_dependencies_{os.getpid()}_{id(object())}"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class DependencyReadinessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = load_runtime()
        self.layout = self.runtime.Layout(
            user_home=self.root / "home",
            codex_home=self.root / "home/.codex",
            agents_home=self.root / "home/.agents",
            state_home=self.root / "home/.codex-sync",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def skill(self, namespace: str, name: str) -> Path:
        root = {
            "agents": self.layout.agents_home / "skills",
            "codex": self.layout.codex_home / "skills",
        }[namespace] / name
        root.mkdir(parents=True, exist_ok=True)
        (root / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        return root

    def manifest(
        self,
        root: Path,
        *,
        requires: list[str] | None = None,
        optional: list[str] | None = None,
        **extra: object,
    ) -> None:
        document = {
            "schema": self.runtime.DEPENDENCY_SCHEMA,
            "requires": ["runtime.python3"] if requires is None else requires,
            "optional": [] if optional is None else optional,
            **extra,
        }
        (root / "dependencies.json").write_text(
            json.dumps(document), encoding="utf-8"
        )

    @staticmethod
    def fingerprint(root: Path) -> dict[str, tuple[int, bytes]]:
        return {
            path.relative_to(root).as_posix(): (path.stat().st_mtime_ns, path.read_bytes())
            for path in root.rglob("*")
            if path.is_file() and not path.is_symlink()
        }

    def test_discovers_skills_from_both_roots_and_validates_selectors(self) -> None:
        self.skill("agents", "agent-tool")
        self.skill("codex", "codex-tool")
        hidden = self.skill("codex", ".hidden")
        system = self.skill("agents", ".system")
        self.assertTrue(hidden.exists())
        self.assertTrue(system.exists())

        discovered = self.runtime.discover_skills(self.layout)
        self.assertEqual(
            ["agents/skills/agent-tool", "codex/skills/codex-tool"],
            [item.logical_id for item in discovered],
        )
        selected = self.runtime.discover_skills(
            self.layout, ["AGENT-TOOL", "codex/skills/codex-tool"]
        )
        self.assertEqual(
            ["agents/skills/agent-tool", "codex/skills/codex-tool"],
            [item.logical_id for item in selected],
        )
        with self.assertRaisesRegex(self.runtime.SyncError, "Unknown Skill selector"):
            self.runtime.discover_skills(self.layout, ["does-not-exist"])

    def test_manifest_schema_rejects_unknown_fields_and_duplicate_keys(self) -> None:
        root = self.skill("agents", "manifest-skill")
        ref = self.runtime.SkillRef("agents/skills", "manifest-skill", root)

        self.manifest(root, unexpected=True)
        present, needs, issues = self.runtime.load_dependency_needs(ref)
        self.assertTrue(present)
        self.assertEqual([], needs)
        self.assertEqual(["unknown manifest field(s): unexpected"], issues)

        self.manifest(root, requires=["runtime.python3"], optional=[])
        present, needs, issues = self.runtime.load_dependency_needs(ref)
        self.assertTrue(present)
        self.assertEqual([], issues)
        self.assertEqual(
            [("runtime.python3", True, "manifest")],
            [(item.dependency_id, item.required, item.source) for item in needs],
        )

        (root / "dependencies.json").write_text(
            "{" 
            '\"schema\": \"codex-sync.skill-dependencies/v1\", '
            '\"requires\": [], \"requires\": [], \"optional\": []}' ,
            encoding="utf-8",
        )
        present, needs, issues = self.runtime.load_dependency_needs(ref)
        self.assertTrue(present)
        self.assertEqual([], needs)
        self.assertEqual(1, len(issues))
        self.assertIn("duplicate key: requires", issues[0])

        self.manifest(root, requires=[], optional=[])
        raw = json.loads((root / "dependencies.json").read_text(encoding="utf-8"))
        raw["schema"] = "codex-sync.skill-dependencies/v0"
        (root / "dependencies.json").write_text(json.dumps(raw), encoding="utf-8")
        _, needs, issues = self.runtime.load_dependency_needs(ref)
        self.assertEqual([], needs)
        self.assertEqual(
            [f"schema must equal {self.runtime.DEPENDENCY_SCHEMA}"], issues
        )

    def test_python_import_inference_distinguishes_catalog_stdlib_local_and_unmanaged(self) -> None:
        root = self.skill("codex", "import-skill")
        (root / "scripts").mkdir()
        (root / "scripts/local_module.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / "main.py").write_text(
            "import json\n"
            "import httpx.client\n"
            "from bs4 import BeautifulSoup\n"
            "from scripts import local_module\n"
            "import definitely_missing_dependency_for_codex_sync\n",
            encoding="utf-8",
        )
        ref = self.runtime.SkillRef("codex/skills", "import-skill", root)

        needs, warnings, unmanaged = self.runtime.inferred_python_needs(ref)
        self.assertEqual([], warnings)
        self.assertEqual(
            ["python.beautifulsoup4", "python.httpx"],
            [item.dependency_id for item in needs],
        )
        self.assertEqual(
            ["python-import:bs4", "python-import:httpx"],
            [item.source for item in needs],
        )
        self.assertEqual(
            ["definitely_missing_dependency_for_codex_sync"],
            [item["module"] for item in unmanaged],
        )
        self.assertEqual("missing_unmanaged", unmanaged[0]["status"])

    def test_status_scan_is_stable_and_read_only(self) -> None:
        agent = self.skill("agents", "agent-ready")
        codex = self.skill("codex", "codex-ready")
        self.manifest(agent)
        self.manifest(codex)
        before = self.fingerprint(self.root)

        first = self.runtime.dependency_scan_document(self.layout, host="macos")
        middle = self.fingerprint(self.root)
        second = self.runtime.dependency_scan_document(self.layout, host="macos")
        after = self.fingerprint(self.root)

        self.assertEqual(before, middle)
        self.assertEqual(middle, after)
        self.assertEqual(first, second)
        self.assertTrue(first["fully_verified"])
        self.assertEqual(2, first["counts"]["skills"])
        self.assertEqual(
            ["agents/skills/agent-ready", "codex/skills/codex-ready"],
            [item["skill"] for item in first["skills"]],
        )

    def test_plan_is_stable_and_stale_install_plan_starts_no_installer(self) -> None:
        root = self.skill("agents", "needs-install")
        self.manifest(root, requires=["python.httpx"])

        def missing_probe(dependency_id: str, host: str) -> dict:
            entry = self.runtime.DEPENDENCY_CATALOG[dependency_id]
            return {
                "dependency_id": dependency_id,
                "kind": entry["kind"],
                "status": "missing",
                "detail": "mocked missing dependency",
            }

        with mock.patch.object(self.runtime, "dependency_platform", return_value="macos"), \
             mock.patch.object(self.runtime, "probe_dependency", side_effect=missing_probe), \
             mock.patch.object(
                 self.runtime, "dependency_manager_executable", return_value="/mock/python"
             ):
            first, _ = self.runtime.dependency_plan_document(self.layout, host="macos")
            second, _ = self.runtime.dependency_plan_document(self.layout, host="macos")
            self.assertEqual(first, second)
            self.assertEqual(1, first["counts"]["install"])

            self.manifest(root, requires=["python.lxml"])
            args = argparse.Namespace(
                deps_command="install", skill=[], plan=first["plan_id"], json=False
            )
            with mock.patch.object(self.runtime, "execute_dependency_actions") as install:
                with self.assertRaisesRegex(self.runtime.SyncError, "Dependency plan changed"):
                    self.runtime.cmd_deps(args, self.layout)
            install.assert_not_called()

    def test_mac_and_windows_install_argv_are_controlled_argument_vectors(self) -> None:
        def executable(manager: str, host: str) -> str:
            return f"/mock-tools/{host}/{manager}"

        with mock.patch.object(
            self.runtime, "dependency_manager_executable", side_effect=executable
        ):
            pip_argv, pip_command = self.runtime.dependency_install_argv(
                "pip", "example-package", "macos"
            )
            npm_argv, _ = self.runtime.dependency_install_argv("npm", "tool", "macos")
            brew_argv, _ = self.runtime.dependency_install_argv("brew", "jq", "macos")
            winget_argv, winget_command = self.runtime.dependency_install_argv(
                "winget", "Vendor.Tool", "windows"
            )

        self.assertEqual(
            ["/mock-tools/macos/pip", "-m", "pip", "--isolated", "install"],
            pip_argv[:5],
        )
        self.assertIn("--disable-pip-version-check", pip_argv)
        self.assertIn("--no-input", pip_argv)
        self.assertIn("--only-binary=:all:", pip_argv)
        self.assertNotIn("--user", pip_argv)
        self.assertNotIn("--break-system-packages", pip_argv)
        self.assertIn("--target", pip_argv)
        self.assertEqual(
            self.runtime.dependency_python_target(),
            pip_argv[pip_argv.index("--target") + 1],
        )
        self.assertEqual("https://pypi.org/simple", pip_argv[pip_argv.index("--index-url") + 1])
        self.assertEqual("example-package", pip_argv[-1])
        self.assertTrue(
            pip_command.startswith("/mock-tools/macos/pip -m pip --isolated install")
        )
        self.assertEqual(
            ["/mock-tools/macos/npm", "install", "--global", "--ignore-scripts",
             "--registry", "https://registry.npmjs.org/", "tool"],
            npm_argv,
        )
        self.assertEqual(["/mock-tools/macos/brew", "install", "jq"], brew_argv)
        self.assertEqual(
            ["/mock-tools/windows/winget", "install", "--id", "Vendor.Tool", "--exact",
             "--source", "winget", "--accept-source-agreements"],
            winget_argv,
        )
        self.assertIn("winget install --id Vendor.Tool", winget_command)

    def test_execute_uses_shell_false_and_rechecks_probe_after_mocked_install(self) -> None:
        action = {
            "action": "install",
            "dependency_id": "python.httpx",
            "_argv": ["/mock/python", "-m", "pip", "install", "httpx"],
            "command": "python3 -m pip install httpx",
        }
        completed = type("Completed", (), {"returncode": 0})()
        ready = {
            "dependency_id": "python.httpx",
            "kind": "python_module",
            "status": "ready",
            "detail": "mocked probe success",
        }
        with mock.patch.object(self.runtime.subprocess, "run", return_value=completed) as run, \
             mock.patch.object(self.runtime, "probe_dependency", return_value=ready) as probe, \
             mock.patch.object(self.runtime.importlib, "invalidate_caches") as invalidate, \
             mock.patch.dict(
                 self.runtime.os.environ,
                 {
                     "PIP_INDEX_URL": "https://example.invalid/simple",
                     "NPM_CONFIG_REGISTRY": "https://example.invalid/",
                     "NODE_OPTIONS": "--require=/tmp/inject.js",
                     "PYTHONPATH": "/tmp/inject",
                     "PYTHONUSERBASE": "/tmp/inject-user-base",
                     "PYTHONNOUSERSITE": "1",
                 },
             ):
            self.runtime.execute_dependency_actions([action], "macos")

        run.assert_called_once()
        self.assertEqual(action["_argv"], run.call_args.args[0])
        self.assertIs(False, run.call_args.kwargs["shell"])
        self.assertIs(False, run.call_args.kwargs["check"])
        environment = run.call_args.kwargs["env"]
        self.assertIsInstance(environment, dict)
        self.assertNotIn("PIP_INDEX_URL", environment)
        self.assertNotIn("NPM_CONFIG_REGISTRY", environment)
        self.assertNotIn("NODE_OPTIONS", environment)
        self.assertNotIn("PYTHONPATH", environment)
        self.assertNotIn("PYTHONUSERBASE", environment)
        self.assertNotIn("PYTHONNOUSERSITE", environment)
        probe.assert_called_once_with("python.httpx", "macos")
        invalidate.assert_called_once_with()

        missing = dict(ready, status="missing", detail="still unavailable")
        with mock.patch.object(self.runtime.subprocess, "run", return_value=completed), \
             mock.patch.object(self.runtime, "probe_dependency", return_value=missing):
            with self.assertRaisesRegex(
                self.runtime.SyncError,
                "Installation completed but verification failed for python.httpx: still unavailable",
            ):
                self.runtime.execute_dependency_actions([action], "macos")


if __name__ == "__main__":
    unittest.main(verbosity=2)
