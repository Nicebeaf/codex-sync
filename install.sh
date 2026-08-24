#!/bin/sh

set -eu
umask 077

if [ -z "${HOME:-}" ]; then
  echo "ERROR: HOME is not set." >&2
  exit 1
fi

case "$HOME" in
  /*) ;;
  *)
    echo "ERROR: HOME must be an absolute path." >&2
    exit 1
    ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: Python 3.9 or newer is required." >&2
  exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "ERROR: Python 3.9 or newer is required." >&2
  exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir="$script_dir/plugins/codex-sync/skills/codex-sync"
codex_home=${CODEX_HOME:-"$HOME/.codex"}
case "$codex_home" in
  /*) ;;
  *)
    echo "ERROR: CODEX_HOME must be an absolute path when set." >&2
    exit 1
    ;;
esac
skills_dir="$codex_home/skills"
destination="$skills_dir/codex-sync"

if [ ! -f "$source_dir/SKILL.md" ] || [ ! -f "$source_dir/scripts/codex_sync.py" ]; then
  echo "ERROR: Codex Sync Skill files are missing from $source_dir." >&2
  exit 1
fi

mkdir -p "$skills_dir"

if [ -L "$destination" ] || { [ -e "$destination" ] && [ ! -d "$destination" ]; }; then
  echo "ERROR: Refusing to replace non-directory target $destination." >&2
  exit 1
fi

if [ -d "$destination" ] && diff -qr "$source_dir" "$destination" >/dev/null 2>&1; then
  echo "Codex Sync Skill is already current at $destination"
  exit 0
fi

stage_dir=$(mktemp -d "$skills_dir/.codex-sync-install.XXXXXX")
cleanup() {
  rm -rf "$stage_dir"
}
trap cleanup EXIT HUP INT TERM
stage_package="$stage_dir/codex-sync"
mkdir "$stage_package"
cp -R "$source_dir/." "$stage_package/"

if ! python3 "$stage_package/scripts/codex_sync.py" --help >/dev/null; then
  echo "ERROR: Staged runtime failed its self-check; the existing installation was not changed." >&2
  exit 1
fi

backup=""
if [ -d "$destination" ]; then
  backup="$skills_dir/.codex-sync-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
  mv "$destination" "$backup"
fi
if ! mv "$stage_package" "$destination"; then
  if [ -n "$backup" ] && [ -d "$backup" ]; then
    mv "$backup" "$destination"
  fi
  echo "ERROR: Installation failed; the previous installation was restored." >&2
  exit 1
fi

echo "Installed Codex Sync Skill at $destination"
if [ -n "$backup" ]; then
  echo "Previous installation preserved at $backup"
fi
echo "Restart Codex if the Skill does not appear immediately."
