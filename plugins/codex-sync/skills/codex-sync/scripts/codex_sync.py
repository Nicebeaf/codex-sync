#!/usr/bin/env python3
"""Conflict-safe synchronization for user-authored Codex data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import stat
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable

VERSION = 1
TOOL_VERSION = "0.4.0"
VALID_SYNC_SCOPES = ("skills", "all")
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_FILES = 10_000
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_DEVICES = 1_000
MAX_JSON_BYTES = 16 * 1024 * 1024
TOKEN_RE = re.compile(r"^[a-f0-9]{16}$")
SNAPSHOT_RE = re.compile(r"^[0-9]{8}T[0-9]{12}Z-[a-f0-9]{8}$")
EXCLUDED_DIRS = {
    ".git", ".system", ".tmp", "__pycache__", "node_modules", ".venv",
    "cache", "caches", "logs", "sessions", "archived_sessions", "plugins",
    "generated_images", "computer-use", "browser",
}
EXCLUDED_SUFFIXES = {
    ".pyc", ".sqlite", ".sqlite3", ".db", ".wal", ".shm", ".log",
    ".pem", ".key", ".p12", ".pfx", ".kdbx", ".jks", ".keystore",
}
EXCLUDED_NAMES = {
    ".ds_store", ".env", ".git-credentials", ".netrc", ".npmrc", ".pypirc",
    "auth.json", "config.toml", "credentials.json", "history.jsonl",
    "id_dsa", "id_ecdsa", "id_ed25519", "id_rsa", "secrets.json",
}
SENSITIVE_NAME = re.compile(
    r"(^|[._-])(api[_-]?key|credential|credentials|password|passwd|private[_-]?key|"
    r"refresh[_-]?token|secret|secrets|access[_-]?token)([._-]|$)",
    re.IGNORECASE,
)
SENSITIVE_FIELD_NAMES = frozenset({
    "accesskey",
    "accesskeyid",
    "accesstoken",
    "apikey",
    "authorization",
    "authtoken",
    "bearertoken",
    "clientsecret",
    "credential",
    "credentials",
    "encryptionkey",
    "jwt",
    "jwttoken",
    "oauth",
    "oauthtoken",
    "password",
    "passwd",
    "passphrase",
    "privatekey",
    "privatekeyid",
    "refreshtoken",
    "secret",
    "secrets",
    "secretkey",
    "serviceaccountkey",
    "sessiontoken",
    "signingkey",
    "token",
    "webhooksecret",
})
SENSITIVE_FIELD_SUFFIXES = (
    "accesskey",
    "accesstoken",
    "apikey",
    "authtoken",
    "bearertoken",
    "clientsecret",
    "encryptionkey",
    "jwttoken",
    "oauthtoken",
    "password",
    "passwd",
    "passphrase",
    "privatekey",
    "refreshtoken",
    "secret",
    "secretkey",
    "sessiontoken",
    "signingkey",
    "token",
    "webhooksecret",
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)^\s*[\"']?(?P<key>api[_-]?key|authorization|password|passwd|"
    r"private[_-]?key|secret|token|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|bearer[_-]?token|oauth[_-]?token|session[_-]?token|"
    r"webhook[_-]?secret)[\"']?\s*[:=]\s*[\"']?"
    r"(?P<value>[^\s\"'#,:}\]]{8,})",
)
YAML_FIELD_RE = re.compile(
    r"(?m)^\s*(?:-\s*)?(?P<key>[\"'][^\"'\r\n]+[\"']|"
    r"[A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*(?P<value>.*)$"
)
FLOW_FIELD_RE = re.compile(
    r"(?x)(?=[{,]\s*(?P<key>[\"'][^\"'\r\n]+[\"']|"
    r"[A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*(?P<value>\"(?:\\.|[^\"\\])*\"|"
    r"'(?:''|[^'])*'|[^,}]+)(?=\s*[,}]))"
)
SECRET_PLACEHOLDER_WORDS = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:your|replace|insert|enter|example|sample|dummy|fake|"
    r"placeholder|redacted|changeme|change[-_ ]?me|not[-_ ]?set|"
    r"unset|todo|tbd)(?![A-Za-z0-9])"
)
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
SECRET_SHAPES = (
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        rb"(?<![A-Za-z0-9_])(?:"
        rb"sk-[A-Za-z0-9_-]{20,}|"
        rb"gh[pousr]_[A-Za-z0-9]{20,}|"
        rb"github_pat_[A-Za-z0-9_]{20,}|"
        rb"glpat-[A-Za-z0-9_-]{20,}|"
        rb"xox[baprs]-[A-Za-z0-9-]{20,}|"
        rb"xapp-[A-Za-z0-9-]{20,}|"
        rb"hf_[A-Za-z0-9_-]{20,}|"
        rb"r8_[A-Za-z0-9_-]{20,}|"
        rb"gsk_[A-Za-z0-9_-]{20,}|"
        rb"pplx-[A-Za-z0-9_-]{20,}|"
        rb"xai-[A-Za-z0-9_-]{20,}|"
        rb"npm_[A-Za-z0-9_-]{20,}|"
        rb"pypi-[A-Za-z0-9_-]{20,}|"
        rb"vercel_[A-Za-z0-9_-]{20,}|"
        rb"lin_api_[A-Za-z0-9_-]{20,}|"
        rb"sbp_[A-Za-z0-9_-]{20,}|"
        rb"fal_[A-Za-z0-9_-]{20,}|"
        rb"(?:AKIA|ASIA)[0-9A-Z]{16}|"
        rb"AIza[A-Za-z0-9_-]{20,}|"
        rb"ya29\.[A-Za-z0-9._-]{20,}|"
        rb"dapi[A-Za-z0-9]{20,}"
        rb")(?![A-Za-z0-9_-])"
    ),
    re.compile(
        rb"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
        rb"(?![A-Za-z0-9_-])"
    ),
)


class SyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class Layout:
    user_home: Path
    codex_home: Path
    agents_home: Path
    state_home: Path


@dataclass
class PlanItem:
    rel: str
    action: str
    local_hash: str | None
    shared_hash: str | None
    base_hash: str | None
    reason: str


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


class SharedLock:
    """Best-effort lock for one mounted shared store."""

    def __init__(self, store: Path, device: str):
        self.path = store / ".codex-sync.lock"
        self.device = device
        self.acquired = False

    def __enter__(self) -> "SharedLock":
        try:
            self.path.mkdir(mode=0o700)
            os.chmod(self.path, 0o700)
        except FileExistsError as exc:
            if self.path.is_symlink() or not self.path.is_dir():
                raise SyncError(f"Shared lock path is unsafe: {self.path}") from exc
            owner_path = self.path / "owner.json"
            owner = json_read(owner_path, {}) if owner_path.exists() and not owner_path.is_symlink() else {}
            detail = f" ({owner.get('device')} at {owner.get('created_at')})" if owner else ""
            raise SyncError(f"Shared store is locked{detail}. Do not sync both devices at once.") from exc
        self.acquired = True
        atomic_json_write(self.path / "owner.json", {
            "version": VERSION,
            "device": self.device,
            "pid": os.getpid(),
            "created_at": now_stamp(),
        })
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if not self.acquired:
            return
        owner_path = self.path / "owner.json"
        try:
            if owner_path.exists() and not owner_path.is_symlink():
                owner_path.unlink()
            self.path.rmdir()
        except OSError as cleanup_error:
            if exc_value is None:
                raise SyncError(f"Could not release shared lock: {cleanup_error}") from cleanup_error


def json_read(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SyncError(f"Cannot safely open JSON file: {path}: {exc}") from exc
    try:
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise SyncError(f"Refusing to read JSON from a non-regular file: {path}")
            if info.st_size > MAX_JSON_BYTES:
                raise SyncError(f"JSON file exceeds size limit: {path}")
            raw = handle.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise SyncError(f"JSON file exceeds size limit: {path}")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SyncError(f"Cannot read valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SyncError(f"Expected a JSON object: {path}")
    return value


def atomic_json_write(path: Path, value: dict) -> None:
    if path.is_symlink() or (path.parent.exists() and path.parent.is_symlink()):
        raise SyncError(f"Refusing to write JSON through a symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def normalized_secret_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def is_sensitive_field_name(value: str) -> bool:
    normalized = normalized_secret_field_name(value)
    return normalized in SENSITIVE_FIELD_NAMES or normalized.endswith(
        SENSITIVE_FIELD_SUFFIXES
    )


def strip_yaml_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if quote:
            if quote == '"' and character == "\\" and not escaped:
                escaped = True
                continue
            if character == quote and not escaped:
                quote = None
            escaped = False
            continue
        if character in ('"', "'"):
            quote = character
        elif character == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.strip()


def yaml_scalar(value: str) -> str:
    candidate = strip_yaml_comment(value).strip()
    if candidate.endswith(","):
        candidate = candidate[:-1].rstrip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] == '"':
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            return candidate[1:-1]
        return decoded if isinstance(decoded, str) else candidate
    if len(candidate) >= 2 and candidate[0] == candidate[-1] == "'":
        return candidate[1:-1].replace("''", "'")
    return candidate


def matches_secret_shape(value: str) -> bool:
    encoded = value.encode("utf-8", errors="ignore")
    return any(pattern.search(encoded) is not None for pattern in SECRET_SHAPES)


def looks_like_secret_value(value: object, field_name: str | None = None) -> bool:
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if len(candidate) < 8:
        return False
    if matches_secret_shape(candidate):
        return True
    lowered = candidate.casefold()
    if lowered in {
        "default", "empty", "false", "none", "nil", "null", "password",
        "redacted", "secret", "token", "true", "undefined", "unset",
    }:
        return False
    if candidate.startswith(("${", "{{", "<")) or candidate.endswith(("}}", ">")):
        return False
    if SECRET_PLACEHOLDER_WORDS.search(candidate) is not None:
        return False
    if re.fullmatch(r"[._\-xX0*#]+", candidate):
        return False
    normalized_field = normalized_secret_field_name(field_name or "")
    bearer = re.fullmatch(r"(?i)bearer\s+(\S+)", candidate)
    if bearer:
        return looks_like_secret_value(bearer.group(1), field_name)
    if any(character.isspace() for character in candidate):
        if normalized_field not in {"password", "passwd", "passphrase"}:
            return False
    return True


def json_contains_secret_shape(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and is_sensitive_field_name(key):
                if isinstance(child, str) and looks_like_secret_value(child, key):
                    return True
            if isinstance(child, (dict, list)) and json_contains_secret_shape(child):
                return True
    elif isinstance(value, list):
        return any(json_contains_secret_shape(child) for child in value)
    return False


def yaml_contains_secret_shape(text: str) -> bool:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = YAML_FIELD_RE.match(line)
        if match is None:
            continue
        key = match.group("key").strip("\"'")
        if not is_sensitive_field_name(key):
            continue
        raw_value = strip_yaml_comment(match.group("value")).strip()
        if raw_value.startswith(("|", ">")):
            base_indent = len(line) - len(line.lstrip())
            block: list[str] = []
            for following in lines[index + 1:]:
                if following.strip() and len(following) - len(following.lstrip()) <= base_indent:
                    break
                if following.strip():
                    block.append(following.strip())
            if looks_like_secret_value(" ".join(block), key):
                return True
            continue
        if looks_like_secret_value(yaml_scalar(raw_value), key):
            return True
    for match in FLOW_FIELD_RE.finditer(text):
        key = match.group("key").strip("\"'")
        if is_sensitive_field_name(key) and looks_like_secret_value(
            yaml_scalar(match.group("value")), key
        ):
            return True
    return False


def text_contains_secret_shape(text: str) -> bool:
    if matches_secret_shape(text):
        return True
    stripped = text.lstrip("\ufeff \t\r\n")
    if stripped.startswith(("{", "[")):
        try:
            document = json.loads(stripped)
            structured_secret = json_contains_secret_shape(document)
        except (json.JSONDecodeError, RecursionError):
            pass
        else:
            if structured_secret:
                return True
    for match in SECRET_ASSIGNMENT_RE.finditer(text):
        if looks_like_secret_value(match.group("value"), match.group("key")):
            return True
    return yaml_contains_secret_shape(text)


def secret_content_shape(content: bytes) -> bool:
    if any(pattern.search(content) is not None for pattern in SECRET_SHAPES):
        return True
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    return text_contains_secret_shape(text)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    content = bytearray()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SyncError(f"Cannot safely open file: {path}: {exc}") from exc
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            raise SyncError(f"File changed type or exceeds size limit: {path}")
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            content.extend(chunk)
    if secret_content_shape(bytes(content)):
        raise SyncError(f"Refusing to process secret-shaped content: {path}")
    return digest.hexdigest()


def validate_regular_file(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        return path.stat().st_size <= MAX_FILE_BYTES
    except OSError:
        return False


def excluded(path: Path) -> bool:
    name = path.name.lower()
    return (
        name in EXCLUDED_NAMES
        or name.startswith(".env.")
        or name.startswith("id_rsa_")
        or name.startswith("id_ed25519_")
        or SENSITIVE_NAME.search(name) is not None
        or path.suffix.lower() in EXCLUDED_SUFFIXES
        or any(part.lower() in EXCLUDED_DIRS for part in path.parts)
    )


def contains_secret_shape(path: Path) -> bool:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                return True
            sample = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        return True
    return secret_content_shape(sample)


def iter_tree(root: Path) -> Iterable[Path]:
    if not root.exists() or root.is_symlink():
        return
    if root.is_file():
        if not excluded(Path(root.name)) and validate_regular_file(root) and not contains_secret_shape(root):
            yield root
        return
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirnames[:] = sorted(
            name for name in dirnames
            if name.lower() not in EXCLUDED_DIRS and not (current_path / name).is_symlink()
        )
        for name in sorted(filenames):
            path = current_path / name
            relative = path.relative_to(root)
            if excluded(relative) or not validate_regular_file(path) or contains_secret_shape(path):
                continue
            yield path


def resolve_user_path(raw: str, user_home: Path) -> Path:
    if raw == "icloud":
        if sys.platform != "darwin":
            raise SyncError(
                "The 'icloud' shortcut is available only on macOS. "
                "Use an absolute shared-folder path on this device."
            )
        return user_home / "Library/Mobile Documents/com~apple~CloudDocs/CodexSync"
    if raw == "onedrive":
        one_drive = next(
            (
                os.environ.get(name)
                for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")
                if os.environ.get(name)
            ),
            None,
        )
        if not one_drive:
            raise SyncError(
                "The 'onedrive' shortcut is not configured. "
                "Use the absolute path to a shared OneDrive folder."
            )
        return (Path(one_drive) / "CodexSync").resolve(strict=False)
    expanded = raw.replace("$HOME", str(user_home))
    if expanded.startswith("~/"):
        expanded = str(user_home / expanded[2:])
    path = Path(expanded)
    if not path.is_absolute():
        raise SyncError(
            "Shared store must be an absolute path or a supported shortcut: "
            "'icloud' on macOS or 'onedrive' when OneDrive is configured."
        )
    return path.resolve(strict=False)


def make_layout(args: argparse.Namespace) -> Layout:
    user_home = Path(args.user_home).expanduser().resolve(strict=False) if args.user_home else Path.home().resolve(strict=False)
    if args.codex_home:
        codex_raw = args.codex_home
    elif args.user_home:
        codex_raw = str(user_home / ".codex")
    else:
        codex_raw = os.environ.get("CODEX_HOME") or str(user_home / ".codex")
    agents_raw = args.agents_home or str(user_home / ".agents")
    state_raw = args.state_home or str(user_home / ".codex-sync")
    return Layout(
        user_home=user_home,
        codex_home=Path(codex_raw).expanduser().resolve(strict=False),
        agents_home=Path(agents_raw).expanduser().resolve(strict=False),
        state_home=Path(state_raw).expanduser().resolve(strict=False),
    )


def config_path(layout: Layout) -> Path:
    return layout.state_home / "config.json"


def state_path(layout: Layout) -> Path:
    return layout.state_home / "state.json"


def store_metadata_path(store: Path) -> Path:
    return store / "store.json"


def legacy_store_id(store: Path, metadata: dict) -> str:
    del store
    seed = canonical_hash({
        "kind": metadata.get("kind"),
        "version": metadata.get("version"),
        "created_at": metadata.get("created_at"),
    })
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def load_store_metadata(store: Path) -> dict:
    path = store_metadata_path(store)
    if not path.exists() or path.is_symlink() or not path.is_file():
        raise SyncError(f"Shared store is not initialized: {path}. Use create on the first device.")
    metadata = json_read(path, {})
    if metadata.get("kind") != "codex-sync" or metadata.get("version") != VERSION:
        raise SyncError(f"Shared store metadata is invalid or unsupported: {path}")
    store_id = metadata.get("store_id")
    if store_id is None:
        metadata["store_id"] = legacy_store_id(store, metadata)
    else:
        try:
            metadata["store_id"] = str(uuid.UUID(str(store_id)))
        except ValueError as exc:
            raise SyncError(f"Shared store ID is invalid: {store_id}") from exc
    return metadata


def ensure_store_metadata_locked(store: Path) -> dict:
    metadata = load_store_metadata(store)
    path = store_metadata_path(store)
    persisted = json_read(path, {})
    if persisted.get("store_id") != metadata["store_id"]:
        persisted["store_id"] = metadata["store_id"]
        persisted["updated_at"] = now_stamp()
        atomic_json_write(path, persisted)
    return metadata


def device_id_for(config: dict, layout: Layout) -> str:
    raw = config.get("device_id")
    if raw:
        try:
            return str(uuid.UUID(str(raw)))
        except ValueError as exc:
            raise SyncError(f"Local device ID is invalid: {raw}") from exc
    seed = f"codex-sync-device:{config['store']}:{config['device']}:{layout.user_home}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def canonical_hash(value: object, length: int = 64) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def validate_device_name(value: str | None) -> str:
    name = (value or platform.node() or "mac").strip()
    if not name or len(name) > 100 or any(ord(character) < 32 for character in name):
        raise SyncError("Device name must be 1-100 printable characters.")
    return name


def validate_sync_scope(value: str | None, *, default: str = "skills") -> str:
    scope = value or default
    if scope not in VALID_SYNC_SCOPES:
        raise SyncError(
            f"Sync scope must be one of: {', '.join(VALID_SYNC_SCOPES)}."
        )
    return scope


def configured_store(layout: Layout, config: dict) -> tuple[Path, dict]:
    store = Path(config["store"])
    assert_safe_store(store, layout)
    metadata = load_store_metadata(store)
    configured_id = config.get("store_id")
    if configured_id and configured_id != metadata["store_id"]:
        raise SyncError(
            "The shared folder now identifies as a different Codex Sync store. "
            "Refusing to mix its data with this device."
        )
    shared_root = store / "shared"
    if shared_root.is_symlink() or not shared_root.is_dir():
        raise SyncError(f"Shared data directory is missing or unsafe: {shared_root}")
    return store, metadata


def make_config(store: Path, metadata: dict, layout: Layout, args: argparse.Namespace) -> dict:
    stamp = now_stamp()
    return {
        "version": VERSION,
        "store": str(store),
        "store_id": metadata["store_id"],
        "device": validate_device_name(getattr(args, "device", None)),
        "device_id": str(uuid.uuid4()),
        "sync_scope": validate_sync_scope(getattr(args, "scope", None)),
        "include_memories": bool(getattr(args, "include_memories", False)),
        "joined_at": stamp,
    }


def persist_config_identity(layout: Layout, config: dict, metadata: dict) -> None:
    changed = False
    if config.get("store_id") != metadata["store_id"]:
        config["store_id"] = metadata["store_id"]
        changed = True
    canonical_device_id = device_id_for(config, layout)
    if config.get("device_id") != canonical_device_id:
        config["device_id"] = canonical_device_id
        changed = True
    if not config.get("joined_at"):
        config["joined_at"] = now_stamp()
        changed = True
    if changed:
        atomic_json_write(config_path(layout), config)


def device_directory(store: Path) -> Path:
    return store / "devices"


def read_devices(store: Path) -> list[dict]:
    root = device_directory(store)
    if not root.exists():
        return []
    if root.is_symlink() or not root.is_dir():
        raise SyncError(f"Device registry is unsafe: {root}")
    entries = sorted(root.iterdir(), key=lambda candidate: candidate.name)
    if len(entries) > MAX_DEVICES:
        raise SyncError(f"Device registry exceeds limit ({len(entries)} > {MAX_DEVICES})")
    result: list[dict] = []
    for path in entries:
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            raise SyncError(f"Unexpected entry in device registry: {path}")
        try:
            expected_id = str(uuid.UUID(path.stem))
        except ValueError as exc:
            raise SyncError(f"Invalid device registry filename: {path.name}") from exc
        record = json_read(path, {})
        try:
            record_store_id = str(uuid.UUID(str(record.get("store_id"))))
        except ValueError as exc:
            raise SyncError(f"Invalid Store ID in device record: {path}") from exc
        name = record.get("name")
        if not isinstance(name, str) or validate_device_name(name) != name:
            raise SyncError(f"Invalid device name in record: {path}")
        record["sync_scope"] = validate_sync_scope(
            record.get("sync_scope"), default="all"
        )
        last_receipt = record.get("last_receipt")
        if last_receipt is not None and (
            not isinstance(last_receipt, str) or TOKEN_RE.fullmatch(last_receipt) is None
        ):
            raise SyncError(f"Invalid receipt token in device record: {path}")
        if record.get("device_id") != expected_id or record_store_id != record.get("store_id"):
            raise SyncError(f"Invalid device record: {path}")
        result.append(record)
    return result


def register_device_locked(
    store: Path,
    metadata: dict,
    config: dict,
    layout: Layout,
    *,
    sync_result: str | None = None,
    plan_id: str | None = None,
    receipt: str | None = None,
) -> None:
    root = device_directory(store)
    mkdir_private(root)
    device_id = device_id_for(config, layout)
    path = root / f"{device_id}.json"
    existing = json_read(path, {}) if path.exists() and not path.is_symlink() else {}
    if not path.exists() and len(read_devices(store)) >= MAX_DEVICES:
        raise SyncError(f"Device registry reached its {MAX_DEVICES}-device limit.")
    stamp = now_stamp()
    record = {
        "version": VERSION,
        "tool_version": TOOL_VERSION,
        "store_id": metadata["store_id"],
        "device_id": device_id,
        "name": config["device"],
        "sync_scope": validate_sync_scope(config.get("sync_scope"), default="all"),
        "joined_at": existing.get("joined_at") or config.get("joined_at") or stamp,
        "last_seen_at": stamp,
        "last_sync_at": existing.get("last_sync_at"),
        "last_result": existing.get("last_result"),
        "last_plan_id": existing.get("last_plan_id"),
        "last_receipt": existing.get("last_receipt"),
    }
    if sync_result is not None:
        record.update({
            "last_sync_at": stamp,
            "last_result": sync_result,
            "last_plan_id": plan_id,
            "last_receipt": receipt,
        })
    atomic_json_write(path, record)


def load_config(layout: Layout) -> dict:
    config = json_read(config_path(layout), {})
    if not config:
        raise SyncError(
            "Not configured. Run 'create --store <path> --device <name>' on the first device "
            "or 'join --store <path> --device <name>' on another device."
        )
    if config.get("version") != VERSION:
        raise SyncError("Unsupported local configuration version.")
    required = {"store", "device", "include_memories"}
    if not required.issubset(config):
        raise SyncError("Local configuration is incomplete; run create or join again.")
    config["device"] = validate_device_name(config.get("device"))
    # Configurations created by 0.2 and earlier synchronized rules and AGENTS.md.
    # Preserve that behavior until the user explicitly selects the safer scope.
    config["sync_scope"] = validate_sync_scope(
        config.get("sync_scope"), default="all"
    )
    device_id_for(config, layout)
    return config


def source_specs(layout: Layout, config: dict) -> list[tuple[str, Path]]:
    specs = [
        ("agents/skills", layout.agents_home / "skills"),
        ("codex/skills", layout.codex_home / "skills"),
    ]
    if validate_sync_scope(config.get("sync_scope"), default="all") == "all":
        specs.extend([
            ("codex/rules", layout.codex_home / "rules"),
            ("codex/AGENTS.md", layout.codex_home / "AGENTS.md"),
        ])
    if config.get("include_memories", False):
        specs.append(("codex/memories", layout.codex_home / "memories"))
    return specs


def rel_is_safe(rel: str, config: dict) -> bool:
    if (
        not isinstance(rel, str)
        or not rel
        or "\\" in rel
        or any(ord(character) < 32 for character in rel)
        or WINDOWS_DRIVE_RE.match(rel) is not None
    ):
        return False
    pure = PurePosixPath(rel)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        return False
    prefixes = ["agents/skills/", "codex/skills/"]
    agents_file_selected = False
    if validate_sync_scope(config.get("sync_scope"), default="all") == "all":
        prefixes.append("codex/rules/")
        agents_file_selected = True
    if config.get("include_memories", False):
        prefixes.append("codex/memories/")
    return (agents_file_selected and rel == "codex/AGENTS.md") or any(
        rel.startswith(prefix) for prefix in prefixes
    )


def target_for(rel: str, layout: Layout, config: dict) -> Path:
    if not rel_is_safe(rel, config):
        raise SyncError(f"Unsafe or unselected shared path: {rel}")
    mappings = [
        ("agents/skills/", layout.agents_home / "skills"),
        ("codex/skills/", layout.codex_home / "skills"),
        ("codex/rules/", layout.codex_home / "rules"),
        ("codex/memories/", layout.codex_home / "memories"),
    ]
    if rel == "codex/AGENTS.md":
        return layout.codex_home / "AGENTS.md"
    for prefix, root in mappings:
        if rel.startswith(prefix):
            return root / PurePosixPath(rel[len(prefix):])
    raise SyncError(f"No local destination for: {rel}")


def collect_local(layout: Layout, config: dict) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for namespace, root in source_specs(layout, config):
        if root.is_file():
            if (
                validate_regular_file(root)
                and not excluded(Path(root.name))
                and not contains_secret_shape(root)
            ):
                result[namespace] = root
            continue
        for path in iter_tree(root):
            rel = path.relative_to(root).as_posix()
            result[f"{namespace}/{rel}"] = path
    validate_collection(result, "local selection")
    return result


def collect_shared(shared_root: Path, config: dict) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in iter_tree(shared_root):
        rel = path.relative_to(shared_root).as_posix()
        if rel_is_safe(rel, config):
            result[rel] = path
    validate_collection(result, "shared selection")
    return result


def validate_collection(paths: dict[str, Path], label: str) -> None:
    if len(paths) > MAX_TOTAL_FILES:
        raise SyncError(f"{label} exceeds file-count limit ({len(paths)} > {MAX_TOTAL_FILES})")
    total = 0
    for path in paths.values():
        try:
            total += path.lstat().st_size
        except OSError as exc:
            raise SyncError(f"Cannot inspect selected file: {path}: {exc}") from exc
        if total > MAX_TOTAL_BYTES:
            raise SyncError(f"{label} exceeds total-size limit ({total} > {MAX_TOTAL_BYTES})")


def hashes(paths: dict[str, Path]) -> dict[str, str]:
    return {rel: hash_file(path) for rel, path in paths.items()}


def plan_sync(layout: Layout, config: dict) -> tuple[list[PlanItem], dict[str, Path], dict[str, Path], dict]:
    shared_root = Path(config["store"]) / "shared"
    local_paths = collect_local(layout, config)
    shared_paths = collect_shared(shared_root, config) if shared_root.exists() else {}
    local_hashes = hashes(local_paths)
    shared_hashes = hashes(shared_paths)
    state = json_read(state_path(layout), {"version": VERSION, "store": config["store"], "files": {}})
    if state.get("store") not in (None, config["store"]):
        raise SyncError("Comparison state belongs to a different shared store. Run configure with the intended store.")
    if (
        state.get("store_id") is not None
        and config.get("store_id") is not None
        and state.get("store_id") != config.get("store_id")
    ):
        raise SyncError("Comparison state belongs to a different shared-store identity.")
    base = state.get("files", {})
    if not isinstance(base, dict):
        raise SyncError("Comparison state is invalid.")
    items: list[PlanItem] = []
    for rel in sorted(set(local_hashes) | set(shared_hashes) | set(base)):
        if not rel_is_safe(rel, config):
            continue
        local_hash = local_hashes.get(rel)
        shared_hash = shared_hashes.get(rel)
        base_hash = base.get(rel)
        if local_hash == shared_hash:
            action, reason = "same", "identical"
        elif base_hash is None:
            if local_hash and not shared_hash:
                action, reason = "push", "new local file"
            elif shared_hash and not local_hash:
                action, reason = "pull", "new shared file"
            else:
                action, reason = "conflict", "different files with no common baseline"
        elif local_hash == base_hash and shared_hash != base_hash:
            action, reason = (("push", "shared deletion is not propagated") if shared_hash is None else ("pull", "shared file changed"))
        elif shared_hash == base_hash and local_hash != base_hash:
            action, reason = (("pull", "local deletion is not propagated") if local_hash is None else ("push", "local file changed"))
        else:
            action, reason = "conflict", "both sides changed"
        items.append(PlanItem(rel, action, local_hash, shared_hash, base_hash, reason))
    return items, local_paths, shared_paths, state


def plan_id_for(
    items: list[PlanItem],
    metadata: dict,
    config: dict,
    expected_receipt: str | None = None,
) -> str:
    payload = {
        "protocol": VERSION,
        "store_id": metadata["store_id"],
        "sync_scope": validate_sync_scope(config.get("sync_scope"), default="all"),
        "include_memories": bool(config.get("include_memories")),
        "expected_receipt": expected_receipt,
        "items": [
            {
                "path": item.rel,
                "action": item.action,
                "local_hash": item.local_hash,
                "shared_hash": item.shared_hash,
                "base_hash": item.base_hash,
            }
            for item in items
        ],
    }
    return canonical_hash(payload, 24)


def shared_tree_hash_for(items: list[PlanItem]) -> str:
    return canonical_hash([
        [item.rel, item.shared_hash]
        for item in items
        if item.shared_hash is not None
    ])


def plan_counts(items: list[PlanItem]) -> dict[str, int]:
    counts = {name: 0 for name in ("push", "pull", "conflict", "same")}
    for item in items:
        counts[item.action] = counts.get(item.action, 0) + 1
    return counts


def plan_document(
    items: list[PlanItem],
    plan_id: str,
    metadata: dict,
    config: dict,
    layout: Layout,
    expected_receipt: str | None,
) -> dict:
    direction = {
        "push": "upload_to_shared_folder",
        "pull": "download_to_this_device",
        "conflict": "not_overwritten",
        "same": "no_change",
    }
    return {
        "schema_version": 1,
        "tool_version": TOOL_VERSION,
        "store": {"id": metadata["store_id"], "path": config["store"]},
        "device": {"id": device_id_for(config, layout), "name": config["device"]},
        "sync_scope": validate_sync_scope(config.get("sync_scope"), default="all"),
        "include_memories": bool(config.get("include_memories")),
        "expected_receipt": expected_receipt,
        "plan_id": plan_id,
        "counts": plan_counts(items),
        "has_conflicts": any(item.action == "conflict" for item in items),
        "items": [
            {
                "path": item.rel,
                "action": item.action,
                "direction": direction[item.action],
                "reason": item.reason,
                "local_hash": item.local_hash,
                "shared_hash": item.shared_hash,
                "base_hash": item.base_hash,
            }
            for item in items
        ],
    }


def receipt_checksum(receipt: dict) -> str:
    unsigned = dict(receipt)
    unsigned.pop("checksum", None)
    return canonical_hash(unsigned)


def load_receipt(store: Path, token: str) -> dict:
    if TOKEN_RE.fullmatch(token) is None:
        raise SyncError("Receipt token must be exactly 16 lowercase hexadecimal characters.")
    root = store / "receipts"
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise SyncError(f"Receipt directory is unsafe: {root}")
    path = root / f"{token}.json"
    if path.is_symlink() or not path.is_file():
        raise SyncError(
            f"Receipt {token} has not arrived in the shared folder. Wait for cloud sync and try again."
        )
    if path.stat().st_size > 64 * 1024:
        raise SyncError(f"Receipt is unexpectedly large: {path}")
    receipt = json_read(path, {})
    if (
        receipt.get("version") != VERSION
        or receipt.get("token") != token
        or receipt.get("checksum") != receipt_checksum(receipt)
    ):
        raise SyncError(f"Receipt {token} is invalid or was changed.")
    try:
        receipt["store_id"] = str(uuid.UUID(str(receipt.get("store_id"))))
        receipt["device_id"] = str(uuid.UUID(str(receipt.get("device_id"))))
    except ValueError as exc:
        raise SyncError(f"Receipt {token} contains an invalid identity.") from exc
    if (
        not isinstance(receipt.get("device"), str)
        or validate_device_name(receipt["device"]) != receipt["device"]
        or not isinstance(receipt.get("plan_id"), str)
        or re.fullmatch(r"[a-f0-9]{24}", receipt["plan_id"]) is None
        or not isinstance(receipt.get("shared_tree_hash"), str)
        or re.fullmatch(r"[a-f0-9]{64}", receipt["shared_tree_hash"]) is None
        or not isinstance(receipt.get("include_memories"), bool)
    ):
        raise SyncError(f"Receipt {token} has invalid fields.")
    receipt["sync_scope"] = validate_sync_scope(
        receipt.get("sync_scope"), default="all"
    )
    return receipt


def verify_expected_receipt(
    store: Path,
    metadata: dict,
    config: dict,
    items: list[PlanItem],
    layout: Layout,
    token: str | None,
) -> dict | None:
    if token is None:
        return None
    receipt = load_receipt(store, token)
    if receipt.get("store_id") != metadata["store_id"]:
        raise SyncError(f"Receipt {token} belongs to a different shared store.")
    if receipt.get("device_id") == device_id_for(config, layout):
        raise SyncError(f"Receipt {token} was created by this same device.")
    records = read_devices(store)
    sender = next(
        (record for record in records if record.get("device_id") == receipt.get("device_id")),
        None,
    )
    if (
        sender is None
        or sender.get("store_id") != metadata["store_id"]
        or sender.get("name") != receipt.get("device")
        or sender.get("last_result") != "success"
        or sender.get("last_receipt") != token
        or sender.get("last_plan_id") != receipt.get("plan_id")
    ):
        raise SyncError(f"Receipt {token} is not the sender device's latest successful handoff.")
    if receipt.get("include_memories") != bool(config.get("include_memories")):
        raise SyncError(f"Receipt {token} was created with a different Memories selection.")
    if receipt.get("sync_scope") != validate_sync_scope(
        config.get("sync_scope"), default="all"
    ):
        raise SyncError(f"Receipt {token} was created with a different sync scope.")
    actual_tree = shared_tree_hash_for(items)
    if receipt.get("shared_tree_hash") != actual_tree:
        raise SyncError(
            f"Receipt {token} arrived but the matching shared files have not. "
            "Wait for cloud sync; no files were changed."
        )
    return receipt


def automatic_expected_receipt(
    store: Path,
    config: dict,
    layout: Layout,
) -> tuple[str | None, dict | None]:
    """Select the newest completed handoff without copying a token manually."""
    records = [
        record
        for record in read_devices(store)
        if isinstance(record.get("last_sync_at"), str)
    ]
    if not records:
        return None, None
    latest = max(
        records,
        key=lambda record: (record.get("last_sync_at", ""), record["device_id"]),
    )
    if latest.get("device_id") == device_id_for(config, layout):
        return None, latest
    if latest.get("last_result") != "success" or not latest.get("last_receipt"):
        raise SyncError(
            f"The latest Store activity came from {latest['name']} with result "
            f"{latest.get('last_result') or 'incomplete'}. Run sync-now on that device "
            "after resolving its conflicts, then wait for the shared folder to finish syncing."
        )
    return latest["last_receipt"], latest


def write_receipt_locked(
    store: Path,
    metadata: dict,
    config: dict,
    layout: Layout,
    plan_id: str,
) -> str:
    receipts = store / "receipts"
    mkdir_private(receipts)
    for _ in range(10):
        token = secrets.token_hex(8)
        path = receipts / f"{token}.json"
        if not path.exists():
            break
    else:
        raise SyncError("Could not allocate a unique receipt token.")
    items, _, _, _ = plan_sync(layout, config)
    receipt = {
        "version": VERSION,
        "tool_version": TOOL_VERSION,
        "token": token,
        "store_id": metadata["store_id"],
        "device_id": device_id_for(config, layout),
        "device": config["device"],
        "plan_id": plan_id,
        "sync_scope": validate_sync_scope(config.get("sync_scope"), default="all"),
        "include_memories": bool(config.get("include_memories")),
        "shared_tree_hash": shared_tree_hash_for(items),
        "created_at": now_stamp(),
    }
    receipt["checksum"] = receipt_checksum(receipt)
    atomic_json_write(path, receipt)
    return token


def ensure_safe_destination(path: Path, allowed_root: Path) -> None:
    root = allowed_root.resolve(strict=False)
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise SyncError(f"Destination escapes allowed root: {path}") from exc
    current = path.parent
    while current != root and current != current.parent:
        if current.exists() and current.is_symlink():
            raise SyncError(f"Refusing to write through symlink: {current}")
        current = current.parent


def ensure_safe_source(path: Path, allowed_root: Path) -> None:
    root = Path(os.path.abspath(allowed_root))
    candidate = Path(os.path.abspath(path))
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SyncError(f"Source escapes allowed root: {path}") from exc
    if root.is_symlink():
        raise SyncError(f"Refusing to read through symlink root: {root}")
    current = candidate.parent
    while current != root and current != current.parent:
        if current.exists() and current.is_symlink():
            raise SyncError(f"Refusing to read through symlink: {current}")
        current = current.parent


def mkdir_private(path: Path) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise SyncError(f"Private directory path is unsafe: {path}")
        return
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        os.chmod(directory, 0o700)


def mkdir_new_private(path: Path) -> None:
    existed = path.exists()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not existed:
        os.chmod(path, 0o700)


def atomic_copy(
    source: Path,
    destination: Path,
    allowed_destination_root: Path,
    allowed_source_root: Path,
    expected_hash: str,
    expected_destination_hash: str | None,
    private_destination: bool = False,
) -> str:
    ensure_safe_source(source, allowed_source_root)
    ensure_safe_destination(destination, allowed_destination_root)
    if private_destination:
        mkdir_private(destination.parent)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        source_fd = os.open(source, flags)
    except OSError as exc:
        raise SyncError(f"Cannot safely open planned source: {source}: {exc}") from exc
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        digest = hashlib.sha256()
        with os.fdopen(source_fd, "rb") as source_handle, os.fdopen(fd, "wb") as destination_handle:
            info = os.fstat(source_handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                raise SyncError(f"Planned source changed type or exceeds size limit: {source}")
            for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                digest.update(chunk)
                destination_handle.write(chunk)
            destination_handle.flush()
            os.fsync(destination_handle.fileno())
        actual_hash = digest.hexdigest()
        if actual_hash != expected_hash:
            raise SyncError(f"Planned source changed after comparison: {source}")
        ensure_safe_destination(destination, allowed_destination_root)
        if destination.is_symlink():
            raise SyncError(f"Destination changed into a symlink after comparison: {destination}")
        if destination.exists():
            actual_destination_hash = hash_file(destination)
        else:
            actual_destination_hash = None
        if actual_destination_hash != expected_destination_hash:
            raise SyncError(f"Destination changed after comparison: {destination}")
        os.chmod(temp_name, 0o600 if private_destination else stat.S_IMODE(info.st_mode) & 0o777)
        os.replace(temp_name, destination)
        return actual_hash
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def backup_copy(
    source: Path,
    source_root: Path,
    backup_root: Path,
    rel: str,
    suffix: str,
    expected_hash: str | None,
) -> None:
    if expected_hash is None:
        return
    destination = backup_root / f"{rel}.{suffix}"
    atomic_copy(
        source,
        destination,
        backup_root,
        source_root,
        expected_hash,
        None,
        private_destination=True,
    )


def print_plan(items: list[PlanItem], plan_id: str, verbose: bool = True) -> None:
    counts = plan_counts(items)
    labels = {
        "push": "UPLOAD  to shared folder",
        "pull": "DOWNLOAD to this device",
        "conflict": "CONFLICT not overwritten",
    }
    for item in items:
        if verbose and item.action != "same":
            print(f"{labels[item.action]:24} {item.rel} ({item.reason})")
    print("Summary: " + ", ".join(f"{key}={counts.get(key, 0)}" for key in ("push", "pull", "conflict", "same")))
    print(f"Plan ID: {plan_id}")


def assert_safe_store(store: Path, layout: Layout) -> None:
    if store == layout.user_home or store in layout.user_home.parents:
        raise SyncError(f"Shared store is too broad: {store}")
    for root in [layout.codex_home, layout.agents_home, layout.state_home]:
        if store == root or root in store.parents or store in root.parents:
            raise SyncError(f"Shared store overlaps protected path: {root}")
    if store == Path(store.anchor):
        raise SyncError("Filesystem root cannot be the shared store.")


def assert_local_setup_available(args: argparse.Namespace, layout: Layout) -> Path:
    path = config_path(layout)
    if path.is_symlink():
        raise SyncError(f"Local configuration path is unsafe: {path}")
    if path.exists() and not getattr(args, "force", False):
        raise SyncError(f"Already configured: {path}. Use configure or add --force.")
    return path


def archive_for_forced_setup(args: argparse.Namespace, layout: Layout) -> None:
    if not getattr(args, "force", False):
        return
    stamp = now_stamp()
    for name in ("config.json", "state.json"):
        source = layout.state_home / name
        if source.exists():
            if source.is_symlink() or not source.is_file():
                raise SyncError(f"Cannot safely replace local setup file: {source}")
            destination = layout.state_home / f"{name[:-5]}.before-setup-{stamp}.json"
            os.replace(source, destination)


def cmd_create(args: argparse.Namespace, layout: Layout) -> int:
    path = assert_local_setup_available(args, layout)
    store = resolve_user_path(args.store, layout.user_home)
    assert_safe_store(store, layout)
    if store.exists():
        if store.is_symlink() or not store.is_dir():
            raise SyncError(f"Shared store path is unsafe: {store}")
        entries = [entry for entry in store.iterdir() if entry.name != ".codex-sync.lock"]
        if entries:
            if store_metadata_path(store).exists():
                raise SyncError("This shared store already exists. Use join on this device.")
            raise SyncError("Create requires a new or empty shared folder; refusing to reuse its contents.")
    mkdir_new_private(store)
    device_name = validate_device_name(args.device)
    with SharedLock(store, device_name):
        unexpected = [entry for entry in store.iterdir() if entry.name != ".codex-sync.lock"]
        if unexpected:
            raise SyncError("Shared folder changed during create; no local setup was written.")
        mkdir_new_private(store / "shared")
        metadata = {
            "version": VERSION,
            "tool_version": TOOL_VERSION,
            "created_at": now_stamp(),
            "kind": "codex-sync",
            "store_id": str(uuid.uuid4()),
        }
        atomic_json_write(store_metadata_path(store), metadata)
        config = make_config(store, metadata, layout, args)
        mkdir_private(layout.state_home)
        archive_for_forced_setup(args, layout)
        atomic_json_write(path, config)
        register_device_locked(store, metadata, config, layout)
    print(f"Created shared store {metadata['store_id']}")
    print(f"Configured {config['device']} at {store}")
    print(f"Sync scope: {config['sync_scope']}")
    print(f"On another device, run: join --store {store} --expect-store-id {metadata['store_id']}")
    print("Next: run doctor once, then use sync-now for routine syncing")
    return 0


def cmd_join(args: argparse.Namespace, layout: Layout) -> int:
    path = assert_local_setup_available(args, layout)
    store = resolve_user_path(args.store, layout.user_home)
    assert_safe_store(store, layout)
    metadata = load_store_metadata(store)
    expected = getattr(args, "expect_store_id", None)
    if expected:
        try:
            expected = str(uuid.UUID(expected))
        except ValueError as exc:
            raise SyncError(f"Expected store ID is invalid: {expected}") from exc
        if expected != metadata["store_id"]:
            raise SyncError(
                f"Wrong shared store: expected {expected}, found {metadata['store_id']}. No setup was changed."
            )
    shared_root = store / "shared"
    if shared_root.is_symlink() or not shared_root.is_dir():
        raise SyncError(f"Shared data directory is missing or unsafe: {shared_root}")
    config = make_config(store, metadata, layout, args)
    with SharedLock(store, config["device"]):
        metadata = ensure_store_metadata_locked(store)
        register_device_locked(store, metadata, config, layout)
        mkdir_private(layout.state_home)
        archive_for_forced_setup(args, layout)
        atomic_json_write(path, config)
    print(f"Joined shared store {metadata['store_id']}")
    print(f"Configured {config['device']} at {store}")
    print(f"Sync scope: {config['sync_scope']}")
    print("Next: run doctor once, then use sync-now for routine syncing")
    return 0


def cmd_init(args: argparse.Namespace, layout: Layout) -> int:
    """Backward-compatible setup: create a missing store, otherwise join it."""
    store = resolve_user_path(args.store, layout.user_home)
    if store_metadata_path(store).exists():
        return cmd_join(args, layout)
    return cmd_create(args, layout)


def cmd_configure(args: argparse.Namespace, layout: Layout) -> int:
    config = load_config(layout)
    old_store = config["store"]
    if args.store:
        store = resolve_user_path(args.store, layout.user_home)
        assert_safe_store(store, layout)
        metadata = load_store_metadata(store)
        if (store / "shared").is_symlink() or not (store / "shared").is_dir():
            raise SyncError(f"Shared data directory is missing or unsafe: {store / 'shared'}")
        config["store"] = str(store)
        config["store_id"] = metadata["store_id"]
    if args.device:
        config["device"] = validate_device_name(args.device)
    if args.scope:
        config["sync_scope"] = validate_sync_scope(args.scope)
    if args.include_memories:
        config["include_memories"] = True
    if args.exclude_memories:
        config["include_memories"] = False
    atomic_json_write(config_path(layout), config)
    if config["store"] != old_store and state_path(layout).exists():
        archived = layout.state_home / f"state.{now_stamp()}.json"
        shutil.copy2(state_path(layout), archived)
        state_path(layout).unlink()
        print(f"Archived comparison state to {archived}")
    store, metadata = configured_store(layout, config)
    with SharedLock(store, config["device"]):
        register_device_locked(store, metadata, config, layout)
    print(json.dumps(config, ensure_ascii=False, indent=2))
    return 0


def cmd_doctor(args: argparse.Namespace, layout: Layout) -> int:
    config = load_config(layout)
    store, metadata = configured_store(layout, config)
    problems: list[str] = []
    if not store.exists() or not store.is_dir():
        problems.append(f"shared store missing: {store}")
    elif not os.access(store, os.R_OK | os.W_OK):
        problems.append(f"shared store is not readable and writable: {store}")
    print(f"Device: {config['device']}")
    print(f"Device ID: {device_id_for(config, layout)}")
    print(f"Store: {store}")
    print(f"Store ID: {metadata['store_id']}")
    print(f"Sync scope: {validate_sync_scope(config.get('sync_scope'), default='all')}")
    print(f"Memories: {'included' if config['include_memories'] else 'excluded'}")
    total = 0
    for namespace, root in source_specs(layout, config):
        count = 1 if root.is_file() else sum(1 for _ in iter_tree(root))
        total += count
        print(f"Selected: {namespace} ({count} files; {'present' if root.exists() else 'missing'})")
    print(f"Total selected files: {total}")
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    print("Doctor: OK")
    return 0


def cmd_status(args: argparse.Namespace, layout: Layout) -> int:
    config = load_config(layout)
    store, metadata = configured_store(layout, config)
    items, _, _, _ = plan_sync(layout, config)
    verify_expected_receipt(store, metadata, config, items, layout, args.expect)
    plan_id = plan_id_for(items, metadata, config, args.expect)
    if args.json:
        print(json.dumps(
            plan_document(items, plan_id, metadata, config, layout, args.expect),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ))
    else:
        print(f"Store ID: {metadata['store_id']}")
        print(f"Sync scope: {config['sync_scope']}")
        print_plan(items, plan_id, verbose=not args.summary_only)
        if args.expect:
            print(f"Receipt confirmed: {args.expect}")
        if any(item.action == "conflict" for item in items):
            print("Conflicts will not be overwritten. Resolve them explicitly before expecting convergence.")
        else:
            print(f"To apply exactly this plan: sync --plan {plan_id}")
    return 2 if any(item.action == "conflict" for item in items) else 0


def allowed_root_for(rel: str, layout: Layout) -> Path:
    if rel.startswith("agents/skills/"):
        return layout.agents_home / "skills"
    if rel.startswith("codex/skills/"):
        return layout.codex_home / "skills"
    if rel.startswith("codex/rules/"):
        return layout.codex_home / "rules"
    if rel.startswith("codex/memories/"):
        return layout.codex_home / "memories"
    if rel == "codex/AGENTS.md":
        return layout.codex_home
    raise SyncError(f"No allowed root for {rel}")


def cmd_sync(args: argparse.Namespace, layout: Layout) -> int:
    config = load_config(layout)
    store, metadata = configured_store(layout, config)
    shared_root = store / "shared"
    if args.dry_run:
        items, _, _, _ = plan_sync(layout, config)
        verify_expected_receipt(store, metadata, config, items, layout, args.expect)
        plan_id = plan_id_for(items, metadata, config, args.expect)
        print_plan(items, plan_id, verbose=True)
        print("Dry run: no files changed")
        return 2 if any(item.action == "conflict" for item in items) else 0
    if not args.plan:
        raise SyncError("A reviewed Plan ID is required. Run status, then sync --plan <PLAN_ID>.")
    with SharedLock(store, config["device"]):
        items, local_paths, shared_paths, state = plan_sync(layout, config)
        verify_expected_receipt(store, metadata, config, items, layout, args.expect)
        actual_plan = plan_id_for(items, metadata, config, args.expect)
        if args.plan != actual_plan:
            raise SyncError(
                f"Plan changed: reviewed {args.plan}, current {actual_plan}. "
                "No selected files were changed; run status again."
            )
        metadata = ensure_store_metadata_locked(store)
        persist_config_identity(layout, config, metadata)
        print_plan(items, actual_plan, verbose=True)
        result = execute_sync(
            layout, config, shared_root, items, local_paths, shared_paths, state
        )
        if result == 0:
            token = write_receipt_locked(store, metadata, config, layout, actual_plan)
            register_device_locked(
                store,
                metadata,
                config,
                layout,
                sync_result="success",
                plan_id=actual_plan,
                receipt=token,
            )
            print(f"Receipt: {token}")
            print(f"On the next device use: status --expect {token}")
        else:
            register_device_locked(
                store,
                metadata,
                config,
                layout,
                sync_result="conflict",
                plan_id=actual_plan,
            )
        return result


def execute_sync(
    layout: Layout,
    config: dict,
    shared_root: Path,
    items: list[PlanItem],
    local_paths: dict[str, Path],
    shared_paths: dict[str, Path],
    state: dict,
) -> int:
    stamp = now_stamp()
    backup_root = layout.state_home / "backups" / stamp
    conflict_root = layout.state_home / "conflicts" / stamp
    new_base = dict(state.get("files", {}))
    conflicts = 0
    changed = 0
    for item in items:
        rel = item.rel
        if item.action == "same":
            if item.local_hash is None:
                new_base.pop(rel, None)
            else:
                new_base[rel] = item.local_hash
            continue
        local_path = local_paths.get(rel) or target_for(rel, layout, config)
        shared_path = shared_paths.get(rel) or (shared_root / PurePosixPath(rel))
        if item.action == "conflict":
            backup_copy(
                local_path, allowed_root_for(rel, layout), conflict_root, rel, "local", item.local_hash
            )
            backup_copy(shared_path, shared_root, conflict_root, rel, "shared", item.shared_hash)
            conflicts += 1
            continue
        if item.action == "push":
            if item.local_hash is None:
                raise SyncError(f"Planned push source disappeared: {rel}")
            backup_copy(
                shared_path, shared_root, backup_root, rel, "before-push", item.shared_hash
            )
            new_base[rel] = atomic_copy(
                local_path,
                shared_path,
                shared_root,
                allowed_root_for(rel, layout),
                item.local_hash,
                item.shared_hash,
            )
            changed += 1
        elif item.action == "pull":
            if item.shared_hash is None:
                raise SyncError(f"Planned pull source disappeared: {rel}")
            backup_copy(
                local_path,
                allowed_root_for(rel, layout),
                backup_root,
                rel,
                "before-pull",
                item.local_hash,
            )
            new_base[rel] = atomic_copy(
                shared_path,
                local_path,
                allowed_root_for(rel, layout),
                shared_root,
                item.shared_hash,
                item.local_hash,
            )
            changed += 1
    atomic_json_write(state_path(layout), {
        "version": VERSION,
        "store": config["store"],
        "store_id": config.get("store_id"),
        "device": config["device"],
        "device_id": device_id_for(config, layout),
        "sync_scope": validate_sync_scope(config.get("sync_scope"), default="all"),
        "updated_at": stamp,
        "files": new_base,
    })
    print(f"Applied {changed} transfer(s); conflicts={conflicts}")
    if conflicts:
        print(f"Conflict copies: {conflict_root}")
        return 2
    return 0


def cmd_sync_now(args: argparse.Namespace, layout: Layout) -> int:
    """Perform one safe routine handoff without manually copying Plan or Receipt IDs."""
    del args
    config = load_config(layout)
    store, metadata = configured_store(layout, config)
    shared_root = store / "shared"
    expected_receipt, sender = automatic_expected_receipt(store, config, layout)
    items, _, _, _ = plan_sync(layout, config)
    verify_expected_receipt(
        store, metadata, config, items, layout, expected_receipt
    )
    plan_id = plan_id_for(items, metadata, config, expected_receipt)
    print(f"Store ID: {metadata['store_id']}")
    print(f"Sync scope: {config['sync_scope']}")
    if expected_receipt and sender:
        print(f"Automatic receipt: {expected_receipt} from {sender['name']}")
    elif sender:
        print(f"Latest Store activity is already from this device: {sender['name']}")
    else:
        print("Automatic receipt: first sync; no previous handoff required")
    print_plan(items, plan_id, verbose=True)
    conflicts = [item for item in items if item.action == "conflict"]
    if conflicts:
        print("Quick sync stopped before changing selected files.", file=sys.stderr)
        for item in conflicts:
            print(f"CONFLICT {item.rel}", file=sys.stderr)
        print(
            "Resolve each conflict explicitly, then run sync-now again.",
            file=sys.stderr,
        )
        return 2

    with SharedLock(store, config["device"]):
        current_receipt, _ = automatic_expected_receipt(store, config, layout)
        if current_receipt != expected_receipt:
            raise SyncError(
                "The latest handoff changed while quick sync was preparing. "
                "No selected files were changed; wait for the shared folder and run sync-now again."
            )
        items, local_paths, shared_paths, state = plan_sync(layout, config)
        verify_expected_receipt(
            store, metadata, config, items, layout, current_receipt
        )
        current_plan_id = plan_id_for(items, metadata, config, current_receipt)
        if current_plan_id != plan_id:
            raise SyncError(
                "The sync plan changed during final verification. "
                "No selected files were changed; run sync-now again."
            )
        if any(item.action == "conflict" for item in items):
            raise SyncError(
                "A conflict appeared during final verification. "
                "No selected files were changed; run sync-now again."
            )
        metadata = ensure_store_metadata_locked(store)
        persist_config_identity(layout, config, metadata)
        result = execute_sync(
            layout, config, shared_root, items, local_paths, shared_paths, state
        )
        if result != 0:
            raise SyncError("Quick sync stopped unexpectedly before creating a receipt.")
        token = write_receipt_locked(
            store, metadata, config, layout, current_plan_id
        )
        register_device_locked(
            store,
            metadata,
            config,
            layout,
            sync_result="success",
            plan_id=current_plan_id,
            receipt=token,
        )
        print("Quick sync complete")
        print(f"Receipt: {token}")
        print("Wait for the shared folder to finish syncing, then run sync-now on the other device.")
        return 0


def cmd_devices(args: argparse.Namespace, layout: Layout) -> int:
    config = load_config(layout)
    store, metadata = configured_store(layout, config)
    records = read_devices(store)
    for record in records:
        if record.get("store_id") != metadata["store_id"]:
            raise SyncError("Device registry contains a record for a different shared store.")
    if args.json:
        print(json.dumps({
            "schema_version": 1,
            "store_id": metadata["store_id"],
            "devices": records,
        }, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Store ID: {metadata['store_id']}")
        if not records:
            print("No devices registered")
        for record in records:
            print(
                f"{record['name']}  {record['device_id']}  "
                f"scope={record.get('sync_scope') or 'all'}  "
                f"last sync={record.get('last_sync_at') or 'never'}  "
                f"result={record.get('last_result') or 'not yet synced'}"
            )
    return 0


def snapshot_root(layout: Layout) -> Path:
    return layout.state_home / "snapshots"


def create_snapshot(layout: Layout, config: dict, kind: str) -> tuple[str, Path, int]:
    files = collect_local(layout, config)
    snapshot_id = f"{now_stamp()}-{secrets.token_hex(4)}"
    destination = snapshot_root(layout) / snapshot_id
    if destination.exists() or destination.is_symlink():
        raise SyncError(f"Snapshot destination already exists or is unsafe: {destination}")
    mkdir_private(snapshot_root(layout))
    staging = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=snapshot_root(layout)))
    os.chmod(staging, 0o700)
    try:
        content_root = staging / "files"
        mkdir_private(content_root)
        manifest: dict[str, str] = {}
        for rel, source in files.items():
            target = content_root / PurePosixPath(rel)
            expected_hash = hash_file(source)
            manifest[rel] = atomic_copy(
                source,
                target,
                content_root,
                allowed_root_for(rel, layout),
                expected_hash,
                None,
                private_destination=True,
            )
        document = {
            "version": VERSION,
            "tool_version": TOOL_VERSION,
            "snapshot_id": snapshot_id,
            "kind": kind,
            "created_at": now_stamp(),
            "store": config["store"],
            "store_id": config.get("store_id"),
            "device": config["device"],
            "device_id": device_id_for(config, layout),
            "sync_scope": validate_sync_scope(config.get("sync_scope"), default="all"),
            "include_memories": bool(config.get("include_memories")),
            "files": manifest,
        }
        document["checksum"] = receipt_checksum(document)
        atomic_json_write(staging / "manifest.json", document)
        os.replace(staging, destination)
    except BaseException:
        if staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging)
        raise
    return snapshot_id, destination, len(files)


def load_snapshot(
    layout: Layout,
    config: dict,
    snapshot_id: str,
    *,
    require_current_store: bool = False,
    require_current_selection: bool = False,
) -> tuple[dict, Path]:
    if SNAPSHOT_RE.fullmatch(snapshot_id) is None:
        raise SyncError(f"Invalid snapshot ID: {snapshot_id}")
    root = snapshot_root(layout) / snapshot_id
    manifest_path = root / "manifest.json"
    content_root = root / "files"
    if root.is_symlink() or not root.is_dir() or content_root.is_symlink() or not content_root.is_dir():
        raise SyncError(f"Snapshot is missing or unsafe: {snapshot_id}")
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise SyncError(f"Snapshot manifest is missing or unsafe: {snapshot_id}")
    manifest = json_read(manifest_path, {})
    if (
        manifest.get("version") != VERSION
        or manifest.get("snapshot_id") != snapshot_id
        or manifest.get("checksum") != receipt_checksum(manifest)
    ):
        raise SyncError(f"Snapshot manifest is invalid or was changed: {snapshot_id}")
    if require_current_store:
        if (
            manifest.get("store_id") is not None
            and config.get("store_id") is not None
            and manifest.get("store_id") != config.get("store_id")
        ):
            raise SyncError(f"Snapshot {snapshot_id} belongs to a different shared Store.")
        if manifest.get("store_id") is None and manifest.get("store") != config.get("store"):
            raise SyncError(f"Snapshot {snapshot_id} belongs to a different shared Store path.")
    files = manifest.get("files")
    if not isinstance(files, dict) or len(files) > MAX_TOTAL_FILES:
        raise SyncError(f"Snapshot file list is invalid: {snapshot_id}")
    snapshot_config = dict(config)
    snapshot_config["sync_scope"] = validate_sync_scope(
        manifest.get("sync_scope"), default="all"
    )
    snapshot_config["include_memories"] = bool(manifest.get("include_memories"))
    total = 0
    for rel, expected_hash in sorted(files.items()):
        if not isinstance(rel, str) or not rel_is_safe(rel, snapshot_config):
            raise SyncError(f"Snapshot contains an unsafe path: {rel!r}")
        if require_current_selection and not rel_is_safe(rel, config):
            raise SyncError(
                f"Snapshot path is not enabled by the current configuration: {rel}. "
                "Enable the matching selection before restore."
            )
        if not isinstance(expected_hash, str) or re.fullmatch(r"[a-f0-9]{64}", expected_hash) is None:
            raise SyncError(f"Snapshot contains an invalid hash for {rel}")
        source = content_root / PurePosixPath(rel)
        ensure_safe_source(source, content_root)
        if source.is_symlink() or not source.is_file() or hash_file(source) != expected_hash:
            raise SyncError(f"Snapshot file is missing or changed: {rel}")
        total += source.stat().st_size
        if total > MAX_TOTAL_BYTES:
            raise SyncError("Snapshot exceeds the total-size limit.")
    return manifest, content_root


def cmd_snapshot(args: argparse.Namespace, layout: Layout) -> int:
    config = load_config(layout)
    snapshot_id, destination, count = create_snapshot(layout, config, "manual")
    print(f"Snapshot {snapshot_id}: {count} file(s) saved to {destination}")
    return 0


def cmd_backup(args: argparse.Namespace, layout: Layout) -> int:
    return cmd_snapshot(args, layout)


def snapshot_history(layout: Layout, config: dict) -> list[dict]:
    root = snapshot_root(layout)
    if not root.exists():
        return []
    if root.is_symlink() or not root.is_dir():
        raise SyncError(f"Snapshot directory is unsafe: {root}")
    entries = sorted(
        (
            path for path in root.iterdir()
            if not path.name.startswith(".snapshot-")
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    if len(entries) > MAX_TOTAL_FILES:
        raise SyncError("Snapshot history exceeds the safety limit.")
    result: list[dict] = []
    for path in entries:
        manifest, _ = load_snapshot(layout, config, path.name)
        result.append({
            "snapshot_id": manifest["snapshot_id"],
            "kind": manifest.get("kind", "manual"),
            "created_at": manifest.get("created_at"),
            "file_count": len(manifest["files"]),
            "device": manifest.get("device"),
        })
    return result


def cmd_history(args: argparse.Namespace, layout: Layout) -> int:
    config = load_config(layout)
    history = snapshot_history(layout, config)
    if args.json:
        print(json.dumps({"schema_version": 1, "snapshots": history}, ensure_ascii=False, indent=2, sort_keys=True))
    elif not history:
        print("No snapshots")
    else:
        for entry in history:
            print(
                f"{entry['snapshot_id']}  {entry['kind']}  "
                f"files={entry['file_count']}  device={entry.get('device') or 'unknown'}"
            )
    return 0


def cmd_restore(args: argparse.Namespace, layout: Layout) -> int:
    config = load_config(layout)
    manifest, content_root = load_snapshot(
        layout,
        config,
        args.id,
        require_current_store=True,
        require_current_selection=True,
    )
    files: dict[str, str] = manifest["files"]
    destination_hashes: dict[str, str | None] = {}
    for rel in sorted(files):
        destination = target_for(rel, layout, config)
        if destination.is_symlink():
            raise SyncError(f"Restore destination is a symlink: {destination}")
        destination_hashes[rel] = hash_file(destination) if destination.exists() else None
    restore_plan = canonical_hash({
        "snapshot_id": args.id,
        "snapshot_checksum": manifest["checksum"],
        "store_id": config.get("store_id"),
        "device_id": device_id_for(config, layout),
        "files": [
            [rel, files[rel], destination_hashes[rel]]
            for rel in sorted(files)
        ],
    }, 24)
    if args.dry_run:
        for rel in sorted(files):
            print(f"RESTORE to this device    {rel}")
        print(f"Dry run: {len(files)} file(s); no files changed")
        print(f"Restore Plan ID: {restore_plan}")
        return 0
    if not args.plan:
        raise SyncError(
            "A reviewed Restore Plan ID is required. Run restore --dry-run, "
            "then restore --plan <RESTORE_PLAN_ID>."
        )
    if args.plan != restore_plan:
        raise SyncError(
            f"Restore plan changed: reviewed {args.plan}, current {restore_plan}. "
            "No files were changed; preview the restore again."
        )
    safety_id, safety_path, safety_count = create_snapshot(layout, config, "before-restore")
    for rel, expected_destination_hash in destination_hashes.items():
        destination = target_for(rel, layout, config)
        actual_hash = hash_file(destination) if destination.exists() and not destination.is_symlink() else None
        if actual_hash != expected_destination_hash:
            raise SyncError(f"Restore destination changed after approval: {rel}")
    restored = 0
    for rel, expected_hash in sorted(files.items()):
        source = content_root / PurePosixPath(rel)
        destination = target_for(rel, layout, config)
        atomic_copy(
            source,
            destination,
            allowed_root_for(rel, layout),
            content_root,
            expected_hash,
            destination_hashes[rel],
        )
        restored += 1
    print(f"Restored {restored} file(s) from snapshot {args.id}")
    print(f"Safety snapshot {safety_id}: {safety_count} file(s) saved to {safety_path}")
    print("No files absent from the snapshot were deleted.")
    return 0


def cmd_resolve(args: argparse.Namespace, layout: Layout) -> int:
    config = load_config(layout)
    rel = PurePosixPath(args.path).as_posix()
    if not rel_is_safe(rel, config):
        raise SyncError(f"Path is not selected or safe: {rel}")
    store, metadata = configured_store(layout, config)
    shared_root = store / "shared"
    with SharedLock(store, config["device"]):
        items, local_paths, shared_paths, state = plan_sync(layout, config)
        item = next((candidate for candidate in items if candidate.rel == rel), None)
        if item is None or item.action != "conflict":
            raise SyncError(f"Path is not currently conflicted: {rel}")
        local_path = local_paths.get(rel) or target_for(rel, layout, config)
        shared_path = shared_paths.get(rel) or (shared_root / PurePosixPath(rel))
        result = execute_resolve(
            args, layout, config, item, state, shared_root, local_path, shared_path
        )
        register_device_locked(
            store,
            metadata,
            config,
            layout,
            sync_result="conflict-resolved",
        )
        return result


def execute_resolve(
    args: argparse.Namespace,
    layout: Layout,
    config: dict,
    item: PlanItem,
    state: dict,
    shared_root: Path,
    local_path: Path,
    shared_path: Path,
) -> int:
    rel = item.rel
    stamp = now_stamp()
    conflict_root = layout.state_home / "conflicts" / f"resolved-{stamp}"
    backup_copy(
        local_path, allowed_root_for(rel, layout), conflict_root, rel, "local", item.local_hash
    )
    backup_copy(shared_path, shared_root, conflict_root, rel, "shared", item.shared_hash)
    if args.prefer == "local":
        if item.local_hash is None:
            raise SyncError("The preferred local side is missing; choose the existing shared side.")
        chosen_hash = atomic_copy(
            local_path,
            shared_path,
            shared_root,
            allowed_root_for(rel, layout),
            item.local_hash,
            item.shared_hash,
        )
    else:
        if item.shared_hash is None:
            raise SyncError("The preferred shared side is missing; choose the existing local side.")
        chosen_hash = atomic_copy(
            shared_path,
            local_path,
            allowed_root_for(rel, layout),
            shared_root,
            item.shared_hash,
            item.local_hash,
        )
    state.setdefault("files", {})[rel] = chosen_hash
    state.update({
        "version": VERSION,
        "store": config["store"],
        "store_id": config.get("store_id"),
        "device": config["device"],
        "device_id": device_id_for(config, layout),
        "sync_scope": validate_sync_scope(config.get("sync_scope"), default="all"),
        "updated_at": stamp,
    })
    atomic_json_write(state_path(layout), state)
    print(f"Resolved {rel} using {args.prefer}; preserved both versions in {conflict_root}")
    return 0


def cmd_unlock(args: argparse.Namespace, layout: Layout) -> int:
    config = load_config(layout)
    store, _ = configured_store(layout, config)
    lock_path = store / ".codex-sync.lock"
    if not lock_path.exists():
        print("Shared store is not locked")
        return 0
    if lock_path.is_symlink() or not lock_path.is_dir():
        raise SyncError(f"Refusing to alter unexpected lock path: {lock_path}")
    owner_path = lock_path / "owner.json"
    owner = json_read(owner_path, {}) if owner_path.exists() and not owner_path.is_symlink() else {}
    print("Lock owner: " + json.dumps(owner, ensure_ascii=False, sort_keys=True))
    if not args.force:
        raise SyncError("Lock remains in place. Re-run unlock --force only after confirming no sync is active.")
    entries = list(lock_path.iterdir())
    if any(entry.name != "owner.json" for entry in entries):
        raise SyncError("Lock directory contains unexpected files; refusing to remove it.")
    if owner_path.exists():
        owner_path.unlink()
    lock_path.rmdir()
    print("Removed stale shared lock")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--version", action="version", version=f"%(prog)s {TOOL_VERSION}")
    result.add_argument("--user-home", help=argparse.SUPPRESS)
    result.add_argument("--codex-home", help=argparse.SUPPRESS)
    result.add_argument("--agents-home", help=argparse.SUPPRESS)
    result.add_argument("--state-home", help=argparse.SUPPRESS)
    sub = result.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a new shared store on the first device")
    create.add_argument("--store", required=True)
    create.add_argument("--device")
    create.add_argument("--scope", choices=VALID_SYNC_SCOPES, default="skills")
    create.add_argument("--include-memories", action="store_true")
    create.add_argument("--force", action="store_true")

    join = sub.add_parser("join", help="join an existing shared store on another device")
    join.add_argument("--store", required=True)
    join.add_argument("--device")
    join.add_argument("--expect-store-id", required=True)
    join.add_argument("--scope", choices=VALID_SYNC_SCOPES, default="skills")
    join.add_argument("--include-memories", action="store_true")
    join.add_argument("--force", action="store_true")

    init = sub.add_parser("init", help="legacy setup command; prefer create or join")
    init.add_argument("--store", required=True)
    init.add_argument("--device")
    init.add_argument("--scope", choices=VALID_SYNC_SCOPES, default="skills")
    init.add_argument("--include-memories", action="store_true")
    init.add_argument("--force", action="store_true")

    configure = sub.add_parser("configure", help="update local configuration")
    configure.add_argument("--store")
    configure.add_argument("--device")
    configure.add_argument("--scope", choices=VALID_SYNC_SCOPES)
    memory = configure.add_mutually_exclusive_group()
    memory.add_argument("--include-memories", action="store_true")
    memory.add_argument("--exclude-memories", action="store_true")

    sub.add_parser("doctor", help="check configuration and selected paths")
    status = sub.add_parser("status", help="show planned actions")
    status.add_argument("--summary-only", action="store_true")
    status.add_argument("--json", action="store_true")
    status.add_argument("--expect", metavar="RECEIPT")
    sync = sub.add_parser("sync", help="apply safe non-conflicting transfers")
    sync.add_argument("--dry-run", action="store_true")
    sync.add_argument("--plan", metavar="PLAN_ID")
    sync.add_argument("--expect", metavar="RECEIPT")
    sub.add_parser(
        "sync-now",
        help="automatically verify the latest handoff and safely sync now",
    )
    sub.add_parser("backup", help="create a local backup of selected files")
    sub.add_parser("snapshot", help="create a restorable local snapshot")
    history = sub.add_parser("history", help="list local snapshots")
    history.add_argument("--json", action="store_true")
    restore = sub.add_parser("restore", help="restore selected files from a local snapshot")
    restore.add_argument("--id", required=True)
    restore.add_argument("--dry-run", action="store_true")
    restore.add_argument("--plan", metavar="RESTORE_PLAN_ID")
    devices = sub.add_parser("devices", help="show devices joined to this shared store")
    devices.add_argument("--json", action="store_true")
    resolve = sub.add_parser("resolve", help="resolve exactly one conflicting file")
    resolve.add_argument("--path", required=True)
    resolve.add_argument("--prefer", choices=("local", "shared"), required=True)
    unlock = sub.add_parser("unlock", help="inspect or remove a stale shared lock")
    unlock.add_argument("--force", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    layout = make_layout(args)
    commands = {
        "create": cmd_create,
        "join": cmd_join,
        "init": cmd_init,
        "configure": cmd_configure,
        "doctor": cmd_doctor,
        "status": cmd_status,
        "sync": cmd_sync,
        "sync-now": cmd_sync_now,
        "backup": cmd_backup,
        "snapshot": cmd_snapshot,
        "history": cmd_history,
        "restore": cmd_restore,
        "devices": cmd_devices,
        "resolve": cmd_resolve,
        "unlock": cmd_unlock,
    }
    try:
        return commands[args.command](args, layout)
    except SyncError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: filesystem operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
