"""jarvis.config.runtime_overrides — process-local runtime config overrides.

OpenClaw parity: mirrors
``openclaw-main/src/config/runtime-overrides.ts``.

Focused minimal port: thin facade with a process-local override tree.
The prototype-key guard is delegated to a caller-provided callable.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Optional

from src.shared.safe_record import is_record_without_throwing  # noqa: F401  (re-export)


#: Process-local override tree.
_overrides: dict = {}


_BLOCKED_KEYS = frozenset({"__proto__", "prototype", "constructor"})


def _is_blocked_object_key(key: str) -> bool:
    return key in _BLOCKED_KEYS


def _is_plain_object(value) -> bool:
    return isinstance(value, dict) and not isinstance(value, (list, tuple, str, bytes, set))


def _sanitize_override_value(value, seen=None) -> Any:
    if seen is None:
        seen = set()
    if isinstance(value, list):
        return [_sanitize_override_value(v, seen) for v in value]
    if not _is_plain_object(value):
        return value
    oid = id(value)
    if oid in seen:
        return {}
    seen.add(oid)
    out: dict = {}
    for k, v in value.items():
        if v is None or _is_blocked_object_key(k):
            continue
        out[k] = _sanitize_override_value(v, seen)
    seen.discard(oid)
    return out


def _merge_overrides(base, override, *, is_blocked_fn: Optional[Callable[[str], bool]] = None) -> Any:
    blocked = is_blocked_fn or _is_blocked_object_key
    if not _is_plain_object(base) or not _is_plain_object(override):
        return override
    next_: dict = dict(base)
    for k, v in override.items():
        if v is None or blocked(k):
            continue
        next_[k] = _merge_overrides(next_.get(k), v, is_blocked_fn=blocked)
    return next_


def get_config_overrides() -> dict:
    """Return the process-local runtime override tree."""
    return _overrides


def reset_config_overrides() -> None:
    """Clear all process-local runtime overrides."""
    global _overrides
    _overrides = {}


def set_config_override(
    path_raw: str,
    value: Any,
    *,
    parse_config_path_fn: Optional[Callable] = None,
    set_config_value_at_path_fn: Optional[Callable] = None,
) -> dict:
    """Set one runtime override at a parsed config path.

    Mirrors :func:`setConfigOverride`
    (``shared/config/runtime-overrides.ts`).
    """
    if not callable(parse_config_path_fn) or not callable(set_config_value_at_path_fn):
        return {"ok": False, "error": "missing runtime hooks"}
    parsed = parse_config_path_fn(path_raw)
    if not parsed.get("ok"):
        return {"ok": False, "error": parsed.get("error") or "parse error"}
    set_config_value_at_path_fn(_overrides, parsed["path"], _sanitize_override_value(value))
    return {"ok": True, "path": parsed["path"]}


def unset_config_override(
    path_raw: str,
    *,
    parse_config_path_fn: Optional[Callable] = None,
    unset_config_value_at_path_fn: Optional[Callable] = None,
) -> dict:
    """Remove one runtime override path and report whether one was present."""
    if not callable(parse_config_path_fn) or not callable(unset_config_value_at_path_fn):
        return {"ok": False, "error": "missing runtime hooks"}
    parsed = parse_config_path_fn(path_raw)
    if not parsed.get("ok"):
        return {"ok": False, "error": parsed.get("error") or "parse error"}
    removed = unset_config_value_at_path_fn(_overrides, parsed["path"])
    return {"ok": True, "removed": bool(removed)}


def apply_config_overrides(cfg: Any) -> Any:
    """Merge the current runtime overrides over a loaded config without mutating the input."""
    if not _overrides:
        return cfg
    return _merge_overrides(cfg, _overrides)


def capture_config_override_applier() -> Callable:
    """Capture an immutable applier for the process-local overrides active at this instant."""
    captured = copy.deepcopy(_overrides) if _overrides else {}
    if not captured:
        return lambda cfg: cfg
    return lambda cfg: _merge_overrides(cfg, captured)


__all__ = [
    "get_config_overrides",
    "reset_config_overrides",
    "set_config_override",
    "unset_config_override",
    "apply_config_overrides",
    "capture_config_override_applier",
]
