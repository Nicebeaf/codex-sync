# Skill dependency readiness

Codex Sync v0.5 checks whether Skills copied to the **current device** have the local runtime, commands, apps, and configured external services they declare. It does not install during a sync, execute a Skill, execute `SKILL.md` prose, fetch a URL from documentation, or run arbitrary scripts. The scan covers user-authored Skills in `~/.agents/skills` and `~/.codex/skills`; `.codex/skills/.system` is excluded.

Dependency readiness is deliberately narrower than a Skill acceptance test. `deps verify` checks catalog probes (for example, whether the `httpx` module is discoverable or a command is on `PATH`) and inferred imports. It does not import third-party modules during discovery. A `verified` probe result is **not** evidence that the Skill's end-to-end business workflow, external authorization, data access, or output quality has been tested.

## Operator workflow

After a successful `sync-now`, run these commands on the receiving device:

```bash
# macOS
python3 scripts/codex_sync.py deps status
python3 scripts/codex_sync.py deps plan
python3 scripts/codex_sync.py deps install --plan "<DEPENDENCY_PLAN_ID>"
python3 scripts/codex_sync.py deps verify
```

```powershell
# Windows PowerShell
py scripts\codex_sync.py deps status
py scripts\codex_sync.py deps plan
py scripts\codex_sync.py deps install --plan "<DEPENDENCY_PLAN_ID>"
py scripts\codex_sync.py deps verify
```

1. `deps status` scans all discovered Skills and reports readiness without changing the system. Use `--json` when structured output is needed.
2. `deps plan` reports a newly computed Dependency Plan ID, the precise supported installation argv rendered as commands, verification probes, required blockers, optional gaps, and legacy advisories. It makes no changes.
3. An operator must show the user that exact Plan ID and every listed command, then obtain explicit approval. Only then run `deps install --plan "<DEPENDENCY_PLAN_ID>"`.
4. `deps install` recomputes the plan before and while holding a local install lock. If the supplied Plan ID differs, no installer starts. Each successful supported installation is probed immediately, then the final scan is printed.
5. `deps verify` repeats the read-only dependency scan. It remains a dependency-probe check, not a business-workflow test.

Use `--skill NAME` or `--skill NAMESPACE/NAME` to limit any dependency command to one discovered Skill. A selector must match a scanned Skill exactly.

## Manifest schema and author contract

Place a UTF-8 JSON file named `dependencies.json` beside the Skill's `SKILL.md`. Publish this complete three-field form:

```json
{
  "schema": "codex-sync.skill-dependencies/v1",
  "requires": ["runtime.python3", "python.httpx"],
  "optional": ["binary.jq"]
}
```

The allowed keys are exactly `schema`, `requires`, and `optional`; no additional keys are accepted. `schema` must equal `codex-sync.skill-dependencies/v1`. `requires` and `optional` are arrays of catalog IDs. An ID must be lowercase and use only letters, digits, `.`, `_`, or `-`; it must be a current catalog ID, may not repeat in an array, and may not appear in both arrays.

Use `requires` for dependencies the Skill needs to be ready. Use `optional` only for feature-specific dependencies; an optional missing dependency yields `ready_optional_missing` with dependency verification `verified`, while the feature that needs it is still unavailable. Keep manifests small, non-secret, and declarative: the reader accepts one safe regular file, strict UTF-8 JSON, no duplicate JSON keys, no secret-shaped content, and at most 16 KiB / 64 total IDs.

A manifest is declarative input to catalog probes and audited installers, not an instruction runner. Do not place shell commands, package URLs, scripts, tokens, provider credentials, or free-text installation instructions in it.

## Built-in catalog (catalog version 1)

All catalog IDs below are authoritative for this runtime. Platform columns show where the catalog can probe the dependency. Install managers are used only when the ID has an audited installer and the manager itself is available.

| Catalog ID | What the probe checks | Platforms | Audited install path |
| --- | --- | --- | --- |
| `runtime.python3` | Python >= 3.9 | macOS, Windows | none; install/configure Python manually |
| `python.beautifulsoup4` | `bs4` module discoverable | macOS, Windows | `pip install beautifulsoup4` |
| `python.httpx` | `httpx` module discoverable | macOS, Windows | `pip install httpx` |
| `python.jinja2` | `jinja2` module discoverable | macOS, Windows | `pip install Jinja2` |
| `python.lxml` | `lxml` module discoverable | macOS, Windows | `pip install lxml` |
| `python.markdown` | `markdown` module discoverable | macOS, Windows | `pip install Markdown` |
| `python.numpy` | `numpy` module discoverable | macOS, Windows | `pip install numpy` |
| `python.openpyxl` | `openpyxl` module discoverable | macOS, Windows | `pip install openpyxl` |
| `python.opencv` | `cv2` module discoverable | macOS, Windows | `pip install opencv-python` |
| `python.pandas` | `pandas` module discoverable | macOS, Windows | `pip install pandas` |
| `python.pillow` | `PIL` module discoverable | macOS, Windows | `pip install Pillow` |
| `python.playwright` | `playwright` module discoverable | macOS, Windows | `pip install playwright` |
| `python.pptx` | `pptx` module discoverable | macOS, Windows | `pip install python-pptx` |
| `python.pyyaml` | `yaml` module discoverable | macOS, Windows | `pip install PyYAML` |
| `python.requests` | `requests` module discoverable | macOS, Windows | `pip install requests` |
| `python.scrapling` | `scrapling` module discoverable | macOS, Windows | `pip install scrapling` |
| `python.scikit-learn` | `sklearn` module discoverable | macOS, Windows | `pip install scikit-learn` |
| `python.weasyprint` | `weasyprint` module discoverable | macOS, Windows | `pip install weasyprint` |
| `python.docx` | `docx` module discoverable | macOS, Windows | `pip install python-docx` |
| `binary.ffmpeg` | `ffmpeg` on `PATH` | macOS, Windows | `brew install ffmpeg` / `winget install --id Gyan.FFmpeg --exact --source winget` |
| `binary.gh` | `gh` on `PATH` | macOS, Windows | `brew install gh` / `winget install --id GitHub.cli --exact --source winget` |
| `binary.git` | `git` on `PATH` | macOS, Windows | `brew install git` / `winget install --id Git.Git --exact --source winget` |
| `binary.jq` | `jq` on `PATH` | macOS, Windows | `brew install jq` / `winget install --id jqlang.jq --exact --source winget` |
| `binary.node` | `node` on `PATH` | macOS, Windows | `brew install node` / `winget install --id OpenJS.NodeJS.LTS --exact --source winget` |
| `binary.pandoc` | `pandoc` on `PATH` | macOS, Windows | `brew install pandoc` / `winget install --id JohnMacFarlane.Pandoc --exact --source winget` |
| `binary.ripgrep` | `rg` on `PATH` | macOS, Windows | `brew install ripgrep` / `winget install --id BurntSushi.ripgrep.MSVC --exact --source winget` |
| `binary.tesseract` | `tesseract` on `PATH` | macOS, Windows | `brew install tesseract` / `winget install --id UB-Mannheim.TesseractOCR --exact --source winget` |
| `binary.yt-dlp` | `yt-dlp` on `PATH` | macOS, Windows | `brew install yt-dlp` / `winget install --id yt-dlp.yt-dlp --exact --source winget` |
| `node.typescript` | `tsc` on `PATH` | macOS, Windows | `npm install --global --ignore-scripts --registry https://registry.npmjs.org/ typescript` |
| `app.final-cut-pro` | `/Applications/Final Cut Pro.app` exists | macOS only | none; install the app manually |
| `mcp.scrapling` | manual local Codex MCP configuration | macOS, Windows | none; configure and authorize locally |

For Python modules, Codex Sync uses the current Python executable with a controlled `-m pip --isolated install` argv so user and environment pip configuration is ignored. Outside a virtual environment it installs with `--target` into that interpreter's user-site directory under the current user's home. This avoids modifying a PEP 668 externally managed Python prefix and does not use `--break-system-packages`; inside a virtual environment it installs into that environment. It also disables pip version checks and input, requires binary distributions, and uses `https://pypi.org/simple`. For npm it uses global installation with `--ignore-scripts` and the npm registry. For winget it uses the exact package ID, the `winget` source, and source-agreement acceptance. The exact rendered command for the active platform is always the Plan output to review.

## States, verification, and blockers

Each discovered Skill has a manifest state and a dependency-verification result:

| Skill state | Verification | Meaning |
| --- | --- | --- |
| `ready` | `verified` | Valid manifest; all required and optional catalog probes are ready; no unmanaged imports or scan warnings. |
| `ready_optional_missing` | `verified` | All required probes are ready; one or more optional catalog dependencies are unavailable. |
| `legacy_unmanaged` | `partial` | No manifest, a present unmanaged import, or a source-scan warning prevents a complete declarative result. |
| `blocked` | `blocked` | A required catalog dependency is missing, unsupported, or manual, or an unknown Python import is missing. |
| `invalid` | `blocked` | The manifest is unsafe or violates the schema/catalog rules. |

Dependency probes themselves can be `ready`, `missing`, `manual`, or `unsupported`. Static Python scanning recognizes standard `import x` and `from x import y` AST statements in safe `.py` files. Standard-library and local modules are ignored. An import that maps to the catalog becomes a required inferred dependency. An unknown import is reported as `present_unmanaged` or `missing_unmanaged`; Codex Sync does not invent a package name or installation command for it.

No `dependencies.json` means `legacy_missing` in the scan and `legacy_unmanaged` / `partial` for that Skill unless another issue blocks it. Documentation-only dependency claims are not guessed. A source parse warning, an unknown import, a manual external dependency, or a platform mismatch is a real evidence boundary: retain `partial` or `blocked` instead of claiming full readiness.

## Installation and safety boundary

`deps install` never executes free-form text from `SKILL.md`, a manifest, a README, a URL, or a bundled script. It can invoke only the audited package-manager argv represented by the reviewed plan:

- Python modules: current Python `-m pip --isolated install` with fixed non-interactive, binary-only PyPI arguments.
- TypeScript: `npm install --global --ignore-scripts` with the fixed npm registry.
- Command-line tools: Homebrew on macOS or winget on Windows with catalog package IDs.
- Applications and external MCP services: reported as manual/blocked; Codex Sync does not automate their installation, sign-in, authorization, or configuration.

Installation is local to the current device. It writes neither the private Sync Store nor a receipt, does not synchronize package state, and does not modify a Skill manifest. Package managers are non-transactional: a failed or interrupted sequence can leave some prior packages installed. They may prompt for elevation, source agreements, or EULA acceptance; treat those prompts as separate local system decisions. The local install lock prevents concurrent Codex Sync dependency installs on one device, but it does not make package managers transactional.

An install command can finish successfully while `deps verify` remains partial because legacy Skills still lack manifests or because an optional/manual dependency remains. Required blockers cause a non-success result; legacy and already-present unmanaged findings are advisories and are never relabeled as fully verified.

## Author migration

1. Inventory the Skill's actual runtime, Python imports, commands, apps, and manually configured services. Do not treat prose in `SKILL.md` as an executable dependency declaration.
2. Match only supported, stable requirements to catalog IDs. Add required IDs to `requires` and feature-specific IDs to `optional`.
3. Add the three-field `dependencies.json` beside `SKILL.md`. For a Skill requiring Python and `httpx`, use the example above.
4. Run `deps status --skill "SKILL_NAME"` and inspect inferred imports. If an import is unknown to the catalog, leave it visible as unmanaged; do not mislabel a guessed package as ready.
5. Run `deps verify --skill "SKILL_NAME"` on macOS and Windows when both platforms are advertised. Record platform-specific manual configuration separately.
6. Test the actual Skill workflow independently. Dependency verification proves only its probes, so release notes and support claims must distinguish probe readiness from full end-to-end validation.

Legacy Skills remain usable; Codex Sync labels them `legacy_unmanaged` rather than making undocumented installation choices. If a dependency has no appropriate catalog ID, document it for maintainers and keep the readiness result partial or blocked until a future audited catalog update exists.

## Package-manager references

- [pip user guide](https://pip.pypa.io/en/stable/user_guide/)
- [npm global package installation](https://docs.npmjs.com/downloading-and-installing-packages-globally/)
- [Homebrew `brew install` manual](https://docs.brew.sh/Manpage)
- [Windows Package Manager `winget install`](https://learn.microsoft.com/windows/package-manager/winget/install)
