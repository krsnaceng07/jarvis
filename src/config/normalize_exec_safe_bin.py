"""jarvis.config.normalize_exec_safe_bin — exec safe-bin config normalizer.

OpenClaw parity: mirrors
``openclaw-main/src/config/normalize-exec-safe-bin.ts``.

Focused minimal port: applies the global and per-agent exec safe-bin
profile normalization. The actual profile fixture / trusted-dir
normalization helpers are delegated to caller-provided callables.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


def normalize_exec_safe_bin_profiles_in_config(
    cfg: Any,
    *,
    normalize_safe_bin_profile_fixtures: Optional[Callable[[Any], Any]] = None,
    normalize_trusted_safe_bin_dirs: Optional[Callable[[Any], Any]] = None,
) -> None:
    """Normalize exec safe-bin profiles and trusted dirs globally + per-agent.

    Mirrors :func:`normalizeExecSafeBinProfilesInConfig`
    (``shared/config/normalize-exec-safe-bin.ts`).
    """
    if not isinstance(cfg, dict):
        return
    def _normalize(exec_value) -> None:
        if not isinstance(exec_value, dict):
            return
        profiles = exec_value.get("safeBinProfiles")
        if callable(normalize_safe_bin_profile_fixtures):
            normalized = normalize_safe_bin_profile_fixtures(profiles or {})
        else:
            normalized = profiles or {}
        if isinstance(normalized, dict) and normalized:
            exec_value["safeBinProfiles"] = normalized
        elif "safeBinProfiles" in exec_value:
            exec_value.pop("safeBinProfiles", None)
        dirs = exec_value.get("safeBinTrustedDirs")
        if callable(normalize_trusted_safe_bin_dirs):
            normalized_dirs = normalize_trusted_safe_bin_dirs(dirs or [])
        else:
            normalized_dirs = dirs or []
        if isinstance(normalized_dirs, list) and normalized_dirs:
            exec_value["safeBinTrustedDirs"] = normalized_dirs
        elif "safeBinTrustedDirs" in exec_value:
            exec_value.pop("safeBinTrustedDirs", None)
    _normalize((cfg.get("tools") or {}).get("exec"))
    agents = (cfg.get("agents") or {}).get("list") or []
    for agent in agents:
        if isinstance(agent, dict):
            _normalize(((agent.get("tools") or {}).get("exec")))


__all__ = ["normalize_exec_safe_bin_profiles_in_config"]
