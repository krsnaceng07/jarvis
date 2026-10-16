"""jarvis.config.io_read_helpers — read-side helpers for the config IO surface.

OpenClaw parity: mirrors ``openclaw-main/src/config/io.read-helpers.ts``.

Focused minimal port: a small set of pure helpers for snapshot hashing,
config coercion, and tilde-path preservation. Heavy logic (env
substitution, includes, dotenv) is delegated to the runtime-installed
config IO subsystem; this module exists so the public surface and the
helper APIs callers depend on are present and importable.
"""
from __future__ import annotations

import hashlib
import os
import re


#: Regex matching a value that starts with `~` followed by end-of-string or a path separator.
_TILDE_PATH_VALUE_RE = re.compile(r"^~(?=$|[/\\])")


#: Regex matching path-like config keys (dir|path|paths|file|root|workspace).
_PATH_LIKE_CONFIG_KEY_RE = re.compile(r"(dir|path|paths|file|root|workspace)$", re.IGNORECASE)


#: Path-like config list keys (matched exactly, not by suffix).
PATH_LIKE_CONFIG_LIST_KEYS = frozenset(["paths", "pathPrepend"])


def _is_path_like_config_key(key):
    """Return whether ``key`` matches the path-like config key shape."""
    if not key:
        return False
    return bool(_PATH_LIKE_CONFIG_KEY_RE.search(key)) or key in PATH_LIKE_CONFIG_LIST_KEYS


def hash_config_raw(raw):
    """Return a stable SHA-256 hex digest of the config raw bytes.

    Mirrors :func:`hashConfigRaw`. ``None`` (missing) is hashed to a
    distinct sentinel so optimistic writes can reject missing-to-empty
    races.
    """
    if raw is None:
        # Distinct sentinel for "missing file"
        return hashlib.sha256(b"\x00__openclaw_missing__").hexdigest()
    if not isinstance(raw, str):
        raw = str(raw)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve_config_snapshot_hash(snapshot):
    """Resolve the canonical hash for a config snapshot, preferring explicit ``hash``."""
    if isinstance(snapshot, dict):
        explicit = snapshot.get("hash")
        if isinstance(explicit, str):
            trimmed = explicit.strip()
            if trimmed:
                return trimmed
        raw = snapshot.get("raw")
        if not isinstance(raw, str):
            return None
        return hash_config_raw(raw)
    return None


def coerce_config(value):
    """Coerce a parsed value to the canonical config shape; ``{}`` for non-objects."""
    if not value or not isinstance(value, dict) or isinstance(value, list):
        return {}
    return value


def has_config_meta(value):
    """Return whether ``value`` has a non-empty ``meta`` object."""
    if not isinstance(value, dict) or isinstance(value, list):
        return False
    meta = value.get("meta")
    return isinstance(meta, dict) and not isinstance(meta, list)


def resolve_gateway_mode(value):
    """Return the trimmed ``gateway.mode`` string or ``None`` if missing/invalid."""
    if not isinstance(value, dict) or isinstance(value, list):
        return None
    gateway = value.get("gateway")
    if not isinstance(gateway, dict) or isinstance(gateway, list):
        return None
    mode = gateway.get("mode")
    if not isinstance(mode, str):
        return None
    trimmed = mode.strip()
    return trimmed or None


def collect_env_ref_paths(value, path_local, output):
    """Walk a value and append dot-paths whose string value contains ``${VAR}`` references.

    Mirrors :func:`collectEnvRefPaths` for callers that want to discover
    every env-substitution site in a config before parsing.
    """
    if isinstance(value, str):
        if "${" in value:
            output[path_local] = value
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            collect_env_ref_paths(item, f"{path_local}[{index}]", output)
        return
    if isinstance(value, dict):
        for key, child in value.items():
            collect_env_ref_paths(child, f"{path_local}.{key}" if path_local else key, output)


#: Sentinel key that marks a config-include directive node.
_INCLUDE_KEY = "$include"


def contains_config_include_directive(value):
    """Return whether the value contains any nested ``$include`` directive node."""
    if isinstance(value, list):
        return any(contains_config_include_directive(item) for item in value)
    if not isinstance(value, dict) or isinstance(value, list):
        return False
    if _INCLUDE_KEY in value:
        return True
    return any(contains_config_include_directive(item) for item in value.values())


def _expand_authored_tilde_path(value: str, home: str) -> str:
    """Expand a tilde-prefixed authored path to an absolute path."""
    suffix = value[1:]
    if not suffix:
        return home
    if suffix.startswith("/") or suffix.startswith("\\"):
        return os.path.join(home, suffix[1:])
    return value


def restore_authored_tilde_paths_for_write(next_value, authored_value, key, home):
    """Restore tilde-prefixed authored form on a path-like key.

    Mirrors :func:`restoreAuthoredTildePathsForWrite`. If the
    next-value (post-expansion) and authored-value (pre-expansion) both
    resolve to the same canonical path, the authored form is preferred
    so the write preserves the operator's original ``~`` form.
    """
    if (
        isinstance(next_value, str)
        and isinstance(authored_value, str)
        and _is_path_like_config_key(key)
        and bool(_TILDE_PATH_VALUE_RE.match(authored_value.strip()))
        and os.path.normpath(next_value) == os.path.normpath(_expand_authored_tilde_path(authored_value.strip(), home))
    ):
        return authored_value
    return next_value


__all__ = [
    "hash_config_raw",
    "resolve_config_snapshot_hash",
    "coerce_config",
    "has_config_meta",
    "resolve_gateway_mode",
    "collect_env_ref_paths",
    "contains_config_include_directive",
    "restore_authored_tilde_paths_for_write",
    "PATH_LIKE_CONFIG_LIST_KEYS",
]
