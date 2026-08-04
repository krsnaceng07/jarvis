"""jarvis.config.legacy — legacy config issue detection.

OpenClaw parity: mirrors ``openclaw-main/src/config/legacy.ts``.

Focused minimal port: the production-built-in rule set is delegated
to a caller-provided ``LEGACY_CONFIG_MIGRATION_RULES`` (the OpenClaw
source imports from ``commands/doctor/shared/legacy-config-migrations``,
which lands separately).
"""
from __future__ import annotations

from typing import Any, List, Optional

from .legacy_shared import LegacyConfigRule


def _get_path_value(root: dict, path: list) -> Any:
    cursor: Any = root
    for key in path:
        if not isinstance(cursor, dict) or cursor is None:
            return None
        cursor = cursor.get(key)
    return cursor


def find_legacy_config_issues(
    raw: Any,
    source_raw: Optional[Any] = None,
    extra_rules: Optional[List[LegacyConfigRule]] = None,
    legacy_rules: Optional[List[LegacyConfigRule]] = None,
    *,
    touched_paths=None,
) -> List[dict]:
    """Find legacy config issues using built-in rules plus optional caller rules.

    Mirrors :func:`findLegacyConfigIssues`
    (``shared/config/legacy.ts``).
    """
    if not isinstance(raw, dict):
        return []
    rules = list(legacy_rules or []) + list(extra_rules or [])
    source_root = source_raw if isinstance(source_raw, dict) else raw
    issues: List[dict] = []
    for rule in rules:
        cursor = _get_path_value(raw, rule.get("path") or [])
        match = rule.get("match")
        if cursor is None or (callable(match) and not match(cursor, raw)):
            continue
        if rule.get("requireSourceLiteral"):
            source_cursor = _get_path_value(source_root, rule.get("path") or [])
            if source_cursor is None:
                continue
            if callable(match) and not match(source_cursor, source_root):
                continue
        issues.append({
            "path": ".".join(rule.get("path") or []),
            "message": rule.get("message") or "",
        })
    return issues


__all__ = ["find_legacy_config_issues"]
