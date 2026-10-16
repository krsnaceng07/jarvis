"""jarvis.config.config_paths — config dot-notation path helpers.

OpenClaw parity: mirrors ``openclaw-main/src/config/config-paths.ts``.
"""
from __future__ import annotations

from typing import Any, TypedDict, Union


#: Subset of prototype-bearing keys blocked from path traversal.
_BLOCKED_KEYS = frozenset({"__proto__", "prototype", "constructor"})


class ParseConfigPathResult(TypedDict, total=False):
    ok: bool
    path: list
    error: str


def _is_blocked_object_key(key: str) -> bool:
    return key in _BLOCKED_KEYS


def _is_plain_object(value) -> bool:
    return isinstance(value, dict) and not isinstance(value, (list, tuple, str))


def parse_config_path(raw: str) -> Union[dict, ParseConfigPathResult]:
    """Parse a CLI/config dot-notation path; rejects unsafe object-key segments.

    Mirrors :func:`parseConfigPath` (``shared/config/config-paths.ts``).
    """
    if not isinstance(raw, str):
        return {"ok": False, "error": "Invalid path. Use dot notation (e.g. foo.bar)."}
    trimmed = raw.strip()
    if not trimmed:
        return {"ok": False, "error": "Invalid path. Use dot notation (e.g. foo.bar)."}
    parts = [p.strip() for p in trimmed.split(".")]
    if not all(parts):
        return {"ok": False, "error": "Invalid path. Use dot notation (e.g. foo.bar)."}
    if any(_is_blocked_object_key(p) for p in parts):
        return {"ok": False, "error": "Invalid path segment."}
    return {"ok": True, "path": parts}


def _set_own_property(node: dict, key: str, value) -> None:
    """Set a key on a plain dict, preserving own-vs-prototype semantics."""
    if key in node:
        node[key] = value
        return
    # Python dicts don't have prototype pollution by default; setting is safe.
    node[key] = value


def set_config_value_at_path(root: dict, path: list, value) -> None:
    """Set a value at a validated config path; create missing plain-object parents.

    Mirrors :func:`setConfigValueAtPath` (``shared/config/config-paths.ts``).
    """
    if not path:
        raise ValueError("Config path must contain at least one segment")
    leaf_key = path[-1]
    cursor: Any = root
    for key in path[:-1]:
        existing = cursor.get(key) if _is_plain_object(cursor) else None
        nxt = existing if _is_plain_object(existing) else {}
        if nxt is not existing:
            _set_own_property(cursor, key, nxt)
        cursor = nxt
    _set_own_property(cursor, leaf_key, value)


def unset_config_value_at_path(root: dict, path: list) -> bool:
    """Remove a value at a config path; prune empty parent objects.

    Mirrors :func:`unsetConfigValueAtPath` (``shared/config/config-paths.ts``).
    """
    if not path or not _is_plain_object(root):
        return False
    leaf_key = path[-1]
    stack: list = []
    cursor: Any = root
    for key in path[:-1]:
        if not _is_plain_object(cursor) or key not in cursor:
            return False
        nxt = cursor[key]
        if not _is_plain_object(nxt):
            return False
        stack.append({"node": cursor, "key": key})
        cursor = nxt
    if leaf_key not in cursor:
        return False
    del cursor[leaf_key]
    for entry in reversed(stack):
        child = entry["node"][entry["key"]]
        if _is_plain_object(child) and len(child) == 0:
            del entry["node"][entry["key"]]
        else:
            break
    return True


def get_config_value_at_path(root: dict, path: list):
    """Read a value at a config path; returns ``None`` at the first non-object parent.

    Mirrors :func:`getConfigValueAtPath` (``shared/config/config-paths.ts``).
    """
    cursor: Any = root
    for key in path:
        if not _is_plain_object(cursor) or key not in cursor:
            return None
        cursor = cursor[key]
    return cursor


__all__ = [
    "parse_config_path",
    "set_config_value_at_path",
    "unset_config_value_at_path",
    "get_config_value_at_path",
]
