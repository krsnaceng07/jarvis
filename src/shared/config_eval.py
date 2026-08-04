"""jarvis.shared.config_eval — config evaluation and runtime eligibility.

OpenClaw parity: mirrors ``openclaw-main/src/shared/config-eval.ts``.
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
from typing import Any, Dict, List, Optional


# Subset of prototype keys that should never be accessed by config-path
# resolution (mirrors the blocked-object-key set).
_BLOCKED_KEYS = frozenset({
    "__proto__", "prototype", "constructor",
})


def is_truthy(value: Any) -> bool:
    """Return whether ``value`` is truthy under requirements-check rules.

    Mirrors the internal ``isTruthy`` predicate (``shared/config-eval.ts``).
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _is_blocked_key(part: str) -> bool:
    return part in _BLOCKED_KEYS


def _resolve_config_path(config: Any, path_str: str) -> Any:
    parts = [p for p in path_str.split(".") if p]
    current: Any = config
    for part in parts:
        if _is_blocked_key(part):
            return None
        if not isinstance(current, dict) or current is None:
            return None
        current = current.get(part)
    return current


def _has_blocked_path_segment(path_str: str) -> bool:
    return any(_is_blocked_key(p) for p in path_str.split(".") if p)


def is_config_path_truthy_with_defaults(
    config: Any, path_str: str, defaults: Optional[Dict[str, bool]] = None
) -> bool:
    """Check a config path with fallback defaults only when the path is unresolved.

    Mirrors :func:`isConfigPathTruthyWithDefaults` (``shared/config-eval.ts``).
    """
    defaults = defaults or {}
    value = _resolve_config_path(config, path_str)
    if (
        value is None
        and not _has_blocked_path_segment(path_str)
        and path_str in defaults
    ):
        return defaults[path_str]
    return is_truthy(value)


def _resolve_runtime_platform() -> str:
    return sys.platform


def _windows_path_extensions() -> List[str]:
    raw = os.environ.get("PATHEXT")
    if raw is not None:
        exts = [e.strip() for e in raw.split(";") if e.strip()]
    else:
        exts = [".EXE", ".CMD", ".BAT", ".COM"]
    return ["", *exts]


_has_binary_cache: Dict[str, bool] = {}
_cached_has_binary_path: Optional[str] = None
_cached_has_binary_path_ext: Optional[str] = None


def has_binary(bin_name: str) -> bool:
    """Check PATH for an executable binary.

    Mirrors :func:`hasBinary` (``shared/config-eval.ts``).
    """
    global _cached_has_binary_path, _cached_has_binary_path_ext
    path_env = os.environ.get("PATH") or ""
    path_ext = os.environ.get("PATHEXT") or "" if sys.platform == "win32" else ""
    if _cached_has_binary_path != path_env or _cached_has_binary_path_ext != path_ext:
        _cached_has_binary_path = path_env
        _cached_has_binary_path_ext = path_ext
        _has_binary_cache.clear()
    if bin_name in _has_binary_cache:
        return _has_binary_cache[bin_name]
    # shutil.which handles Windows PATHEXT correctly.
    found = shutil.which(bin_name) is not None
    _has_binary_cache[bin_name] = found
    return found


def evaluate_runtime_eligibility(
    *,
    os_list: Optional[List[str]] = None,
    remote_platforms: Optional[List[str]] = None,
    always: bool = False,
    requires: Optional[dict] = None,
    has_bin: Any = lambda b: has_binary(b),
    has_remote_bin: Any = None,
    has_any_remote_bin: Any = None,
    has_env: Any = lambda n: bool(os.environ.get(n)),
    is_config_path_truthy: Any = lambda p: True,
) -> bool:
    """Evaluate OS gating and runtime requirements for entry eligibility.

    Mirrors :func:`evaluateRuntimeEligibility` (``shared/config-eval.ts``).
    """
    os_list = os_list or []
    remote_platforms = remote_platforms or []
    if os_list:
        local = _resolve_runtime_platform()
        if local not in os_list and not any(p in os_list for p in remote_platforms):
            return False
    if always:
        return True
    requires = requires or {}
    for bin_name in requires.get("bins") or []:
        if not has_bin(bin_name) and not (has_remote_bin and has_remote_bin(bin_name)):
            return False
    any_bins = requires.get("anyBins") or []
    if any_bins:
        any_local = any(has_bin(b) for b in any_bins)
        if not any_local and not (has_any_remote_bin and has_any_remote_bin(any_bins)):
            return False
    for env_name in requires.get("env") or []:
        if not has_env(env_name):
            return False
    for path in requires.get("config") or []:
        if not is_config_path_truthy(path):
            return False
    return True


__all__ = [
    "is_truthy",
    "is_config_path_truthy_with_defaults",
    "has_binary",
    "evaluate_runtime_eligibility",
]
