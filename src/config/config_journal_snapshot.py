"""jarvis.config.config_journal_snapshot — fingerprinted config snapshot journal.

OpenClaw parity: mirrors
``openclaw-main/src/config/config-journal-snapshot.ts``.

Focused minimal port: HMAC-SHA256 fingerprinting with per-install key,
configurable audit store. The audit store impl is supplied by the caller
until the SQLite audit store port lands.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from typing import Any, Callable, Optional, TypedDict


CONFIG_SNAPSHOT_SCOPE = "config-snapshot"
CONFIG_SNAPSHOT_KEY = "latest"
CONFIG_JOURNAL_FINGERPRINT_KEY_FILENAME = "config-journal-fingerprint.key"
CONFIG_JOURNAL_FINGERPRINT_KEY_BYTES = 32
CONFIG_JOURNAL_REDACTION_MARKER = "***"


class ConfigSnapshotAuditRecord(TypedDict, total=False):
    configPath: str
    rawHash: str
    fingerprintedAuthoredConfig: Any


#: Cache of fingerprint keys by resolved key path.
_config_journal_fingerprint_keys: dict = {}


def _resolve_state_dir(env) -> str:
    state = (env or {}).get("JARVIS_STATE_DIR") or (env or {}).get("OPENCLAW_STATE_DIR")
    if state:
        return os.path.expanduser(state)
    home = (env or {}).get("HOME") or (env or {}).get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(home, ".jarvis")


def _load_config_journal_fingerprint_key(env=None, homedir=None) -> Optional[bytes]:
    env = env if env is not None else dict(os.environ)
    state_dir = _resolve_state_dir(env)
    if homedir is not None:
        # Allow tests to inject a custom home; primarily for offline runs.
        state_dir = state_dir.replace(os.path.expanduser("~"), homedir, 1)
    key_path = os.path.join(state_dir, CONFIG_JOURNAL_FINGERPRINT_KEY_FILENAME)
    cached = _config_journal_fingerprint_keys.get(key_path)
    if cached is not None:
        return cached
    try:
        if not os.path.isfile(key_path):
            os.makedirs(state_dir, mode=0o700, exist_ok=True)
            created = secrets.token_bytes(CONFIG_JOURNAL_FINGERPRINT_KEY_BYTES)
            try:
                fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    os.write(fd, created)
                finally:
                    os.close(fd)
                key = created
            except FileExistsError:
                with open(key_path, "rb") as f:
                    key = f.read()
        else:
            with open(key_path, "rb") as f:
                key = f.read()
    except OSError:
        return None
    if len(key) != CONFIG_JOURNAL_FINGERPRINT_KEY_BYTES:
        return None
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    _config_journal_fingerprint_keys[key_path] = key
    return key


def _fingerprint_value(value: Any, key: Optional[bytes]) -> str:
    if key is None:
        return CONFIG_JOURNAL_REDACTION_MARKER
    try:
        serialized = json.dumps(value)
    except (TypeError, ValueError):
        serialized = str(value)
    digest = hmac.new(key, (serialized or "").encode("utf-8"), hashlib.sha256).hexdigest()
    return f"fp:{digest[:12]}"


def _fingerprint_leaves(value: Any, key: Optional[bytes]) -> Any:
    if isinstance(value, list):
        return [_fingerprint_leaves(v, key) for v in value]
    if isinstance(value, dict):
        return {k: _fingerprint_leaves(v, key) for k, v in value.items()}
    return _fingerprint_value(value, key)


def fingerprint_config_snapshot_authored_config(value: Any, env=None) -> Any:
    """Fingerprint every leaf of an authored config object for diff baselines.

    Mirrors :func:`fingerprintConfigSnapshotAuthoredConfig`
    (``shared/config/config-journal-snapshot.ts``).
    """
    key = _load_config_journal_fingerprint_key(env)
    return _fingerprint_leaves(value, key)


def config_snapshot_audit_record_matches_path(
    snapshot: Optional[ConfigSnapshotAuditRecord], config_path: str
) -> bool:
    if not snapshot:
        return False
    return os.path.normpath(snapshot.get("configPath") or "") == os.path.normpath(config_path)


def _resolve_audit_store(env):
    """Factory: returns a config-snapshot audit-store handle.

    The OpenClaw source wires this to ``createSqliteAuditRecordStore``; the
    Python port accepts a caller-provided store factory until the SQLite
    port lands.
    """
    raise NotImplementedError("audit store wiring lands with infra/sqlite-audit-record-store")


def read_latest_config_snapshot_audit_record(env=None) -> Optional[ConfigSnapshotAuditRecord]:
    try:
        store = _resolve_audit_store(env if env is not None else dict(os.environ))
    except Exception:
        return None
    try:
        for entry in store.entries():
            if entry.get("key") == CONFIG_SNAPSHOT_KEY:
                return entry.get("value")
    except Exception:
        return None
    return None


def upsert_config_snapshot_audit_record(
    *,
    config_path: str,
    raw_hash: str,
    authored_config: Any,
    env=None,
    expected_snapshot: Optional[ConfigSnapshotAuditRecord] = None,
) -> Optional[ConfigSnapshotAuditRecord]:
    snapshot: ConfigSnapshotAuditRecord = {
        "configPath": os.path.normpath(config_path),
        "rawHash": raw_hash,
        "fingerprintedAuthoredConfig": fingerprint_config_snapshot_authored_config(
            authored_config, env
        ),
    }
    try:
        store = _resolve_audit_store(env if env is not None else dict(os.environ))
    except Exception:
        return None
    try:
        if expected_snapshot is not None:
            return snapshot if store.compare_and_set(
                CONFIG_SNAPSHOT_KEY, expected_snapshot, snapshot
            ) else None
        store.upsert(CONFIG_SNAPSHOT_KEY, snapshot)
        return snapshot
    except Exception:
        return None


def restore_config_snapshot_audit_record(
    *,
    snapshot: Optional[ConfigSnapshotAuditRecord],
    env=None,
    expected_snapshot: Optional[ConfigSnapshotAuditRecord] = None,
) -> None:
    try:
        store = _resolve_audit_store(env if env is not None else dict(os.environ))
    except Exception:
        return
    try:
        if expected_snapshot is not None:
            store.compare_and_set(CONFIG_SNAPSHOT_KEY, expected_snapshot, snapshot)
            return
        if snapshot:
            store.upsert(CONFIG_SNAPSHOT_KEY, snapshot)
        else:
            store.delete(CONFIG_SNAPSHOT_KEY)
    except Exception:
        pass


__all__ = [
    "CONFIG_SNAPSHOT_SCOPE",
    "CONFIG_SNAPSHOT_KEY",
    "CONFIG_JOURNAL_FINGERPRINT_KEY_FILENAME",
    "CONFIG_JOURNAL_FINGERPRINT_KEY_BYTES",
    "CONFIG_JOURNAL_REDACTION_MARKER",
    "ConfigSnapshotAuditRecord",
    "fingerprint_config_snapshot_authored_config",
    "config_snapshot_audit_record_matches_path",
    "read_latest_config_snapshot_audit_record",
    "upsert_config_snapshot_audit_record",
    "restore_config_snapshot_audit_record",
]
