"""jarvis.config.normalize_paths — ``~`` path normalization in config fields.

OpenClaw parity: mirrors
``openclaw-main/src/config/normalize-paths.ts``.
"""
from __future__ import annotations

import os
import re
from typing import Any


_PATH_VALUE_RE = re.compile(r"^~(?=$|[\\/])")
_PATH_KEY_RE = re.compile(r"(dir|path|paths|file|root|workspace)$", re.IGNORECASE)
_PATH_LIST_KEYS = frozenset({"paths", "pathPrepend"})


def _is_plain_object(value) -> bool:
    return isinstance(value, dict) and not isinstance(value, (list, tuple, str, bytes, set))


def _resolve_user_path(value: str) -> str:
    """Expand ``~`` in user paths; focused minimal port.

    Mirrors :func:`resolveUserPath`
    (``shared/utils.ts`).
    """
    if not isinstance(value, str) or not value.startswith("~"):
        return value
    return os.path.expanduser(value)


def _normalize_string_value(key, value: str) -> str:
    if not _PATH_VALUE_RE.match((value or "").strip()):
        return value
    if not key:
        return value
    if _PATH_KEY_RE.search(key) or key in _PATH_LIST_KEYS:
        return _resolve_user_path(value)
    return value


def _normalize_any(key, value):
    if isinstance(value, str):
        return _normalize_string_value(key, value)
    if isinstance(value, list):
        normalize_children = bool(key and key in _PATH_LIST_KEYS)
        out: list = []
        for entry in value:
            if isinstance(entry, str):
                out.append(_normalize_string_value(key, entry) if normalize_children else entry)
            elif isinstance(entry, list):
                out.append(_normalize_any(None, entry))
            elif _is_plain_object(entry):
                out.append(_normalize_any(None, entry))
            else:
                out.append(entry)
        return out
    if not _is_plain_object(value):
        return value
    for child_key, child_value in list(value.items()):
        next_value = _normalize_any(child_key, child_value)
        if next_value is not child_value:
            value[child_key] = next_value
    return value


def normalize_config_paths(cfg: Any) -> Any:
    """Normalize ``~`` paths in path-ish config fields.

    Mirrors :func:`normalizeConfigPaths`
    (``shared/config/normalize-paths.ts`).
    """
    if not isinstance(cfg, dict):
        return cfg
    _normalize_any(None, cfg)
    return cfg


__all__ = ["normalize_config_paths"]
