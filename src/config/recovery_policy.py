"""jarvis.config.recovery_policy — config recovery decision helpers.

OpenClaw parity: mirrors
``openclaw-main/src/config/recovery-policy.ts``.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional, TypedDict


_PLUGIN_ENTRY_PATH_PREFIX = "plugins.entries."
_PLUGIN_POLICY_PATHS = frozenset({"plugins.allow", "plugins.deny"})
_COMPILED_RUNTIME_OUTPUT_DIAGNOSTIC = "compiled runtime output"
_PLUGIN_DIAGNOSTIC_PREFIX_RE = re.compile(r"^plugin\s+([^:\s]+):\s", re.UNICODE)
_PLUGIN_NOT_FOUND_RE = re.compile(r"^plugin not found:\s*([^\s(]+)", re.UNICODE)


class ConfigFileSnapshot(TypedDict, total=False):
    valid: bool
    issues: list
    legacyIssues: list
    warnings: list


def _is_plugins_path(path: str) -> bool:
    return path == "plugins" or path.startswith("plugins.")


def _is_plugin_entry_issue(issue: dict) -> bool:
    path = (issue.get("path") or "").strip()
    if not path.startswith(_PLUGIN_ENTRY_PATH_PREFIX):
        return False
    return bool(path[len(_PLUGIN_ENTRY_PATH_PREFIX):].strip())


def _is_plugin_policy_issue(issue: dict) -> bool:
    path = (issue.get("path") or "").strip()
    message = (issue.get("message") or "").strip()
    return path in _PLUGIN_POLICY_PATHS and message.startswith("plugin not found:")


def _is_plugin_packaging_runtime_output_issue(issue: dict) -> bool:
    path = (issue.get("path") or "").strip()
    message = (issue.get("message") or "").strip().lower()
    return _is_plugins_path(path) and _COMPILED_RUNTIME_OUTPUT_DIAGNOSTIC in message


def _is_plugin_packaging_fallout_issue(issue: dict) -> bool:
    path = (issue.get("path") or "").strip()
    message = (issue.get("message") or "").strip()
    return _is_plugins_path(path) and message.startswith("plugin not found:")


def _normalize_plugin_issue_id(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _extract_plugin_packaging_runtime_output_plugin_id(issue: dict) -> Optional[str]:
    if not _is_plugin_packaging_runtime_output_issue(issue):
        return None
    message = (issue.get("message") or "").strip()
    match = _PLUGIN_DIAGNOSTIC_PREFIX_RE.match(message)
    if not match:
        return None
    return _normalize_plugin_issue_id(match.group(1))


def _extract_plugin_not_found_issue_plugin_id(issue: dict) -> Optional[str]:
    if not _is_plugin_packaging_fallout_issue(issue):
        return None
    message = (issue.get("message") or "").strip()
    match = _PLUGIN_NOT_FOUND_RE.match(message)
    if not match:
        return None
    return _normalize_plugin_issue_id(match.group(1))


def is_plugin_packaging_runtime_output_invalid_config_snapshot(snapshot: dict) -> bool:
    """Return True when invalid config is blocked only by plugin packaging fallout.

    Mirrors :func:`isPluginPackagingRuntimeOutputInvalidConfigSnapshot`
    (``shared/config/recovery-policy.ts`).
    """
    if not isinstance(snapshot, dict):
        return False
    if snapshot.get("valid") or len(snapshot.get("legacyIssues") or []) > 0:
        return False
    issues = list(snapshot.get("issues") or [])
    warnings = list(snapshot.get("warnings") or [])
    if not issues:
        return False
    packaging_issues = [i for i in (*issues, *warnings) if _is_plugin_packaging_runtime_output_issue(i)]
    packaging_plugin_ids = {
        pid for pid in (
            _extract_plugin_packaging_runtime_output_plugin_id(i) for i in packaging_issues
        ) if pid is not None
    }
    if not packaging_issues:
        return False
    for issue in issues:
        if _is_plugin_packaging_runtime_output_issue(issue):
            continue
        plugin_id = _extract_plugin_not_found_issue_plugin_id(issue)
        if plugin_id is None or plugin_id not in packaging_plugin_ids:
            return False
    return True


def is_plugin_local_invalid_config_snapshot(snapshot: dict) -> bool:
    """Return True when invalid config is scoped entirely to stale plugin refs."""
    if not isinstance(snapshot, dict):
        return False
    if snapshot.get("valid") or snapshot.get("legacyIssues") or not snapshot.get("issues"):
        return False
    return all(
        _is_plugin_entry_issue(i) or _is_plugin_policy_issue(i)
        for i in (snapshot.get("issues") or [])
    )


def should_attempt_last_known_good_recovery(snapshot: dict) -> bool:
    """Decide whether whole-file last-known-good recovery is appropriate.

    Mirrors :func:`shouldAttemptLastKnownGoodRecovery`
    (``shared/config/recovery-policy.ts`).
    """
    if not isinstance(snapshot, dict) or snapshot.get("valid"):
        return False
    return not is_plugin_local_invalid_config_snapshot(snapshot)


__all__ = [
    "is_plugin_packaging_runtime_output_invalid_config_snapshot",
    "is_plugin_local_invalid_config_snapshot",
    "should_attempt_last_known_good_recovery",
]
