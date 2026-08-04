"""jarvis.config.issue_format — config issue formatter for CLI output.

OpenClaw parity: mirrors
``openclaw-main/src/config/issue-format.ts``.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, TypedDict


_SANITIZE_RE = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize(text: str) -> str:
    """Strip control characters for safe terminal output.

    Mirrors the behavior of OpenClaw's ``sanitizeTerminalText`` helper
    for the fields this module emits.
    """
    if not isinstance(text, str):
        return ""
    return _SANITIZE_RE.sub("", text)


class ConfigValidationIssue(TypedDict, total=False):
    path: str
    message: str
    allowedValues: List[str]
    allowedValuesHiddenCount: int
    pathSegments: list


def normalize_config_issue_path(path) -> str:
    """Normalize missing or blank config issue paths to ``<root>``."""
    if not isinstance(path, str):
        return "<root>"
    trimmed = path.strip()
    return trimmed or "<root>"


def normalize_config_issue(issue: dict) -> dict:
    """Return the public config issue shape with a normalized path."""
    out: dict = {
        "path": normalize_config_issue_path(issue.get("path")),
        "message": issue.get("message") or "",
    }
    if isinstance(issue.get("allowedValues"), list) and issue["allowedValues"]:
        out["allowedValues"] = issue["allowedValues"]
    if (
        isinstance(issue.get("allowedValuesHiddenCount"), int)
        and issue["allowedValuesHiddenCount"] > 0
    ):
        out["allowedValuesHiddenCount"] = issue["allowedValuesHiddenCount"]
    if issue.get("pathSegments") is not None:
        out["pathSegments"] = issue["pathSegments"]
    return out


def normalize_config_issues(issues: Iterable[dict]) -> List[dict]:
    return [normalize_config_issue(i) for i in issues or []]


def _resolve_issue_location_prefix(issue: dict, opts: Optional[dict]) -> str:
    options = opts or {}
    source_file = (
        issue.get("sourceFile")
        if isinstance(issue.get("sourceFile"), str) and issue.get("sourceFile").strip()
        else (options.get("sourceFile") if isinstance(options.get("sourceFile"), str) else "")
    )
    if not source_file:
        return ""
    line = issue.get("line")
    if not isinstance(line, int) or line <= 0:
        return ""
    return f"{_sanitize(source_file)}:{line} — "


def _resolve_issue_path_for_line(path, opts: Optional[dict]) -> str:
    if (opts or {}).get("normalizeRoot"):
        return normalize_config_issue_path(path)
    return path if isinstance(path, str) else ""


def format_config_issue_line(issue: dict, marker: str = "-", opts: Optional[dict] = None) -> str:
    """Format one config issue for terminal output.

    Mirrors :func:`formatConfigIssueLine`
    (``shared/config/issue-format.ts``).
    """
    options = opts or {}
    prefix = f"{marker} " if marker else ""
    location = _resolve_issue_location_prefix(issue, options)
    path = _sanitize(_resolve_issue_path_for_line(issue.get("path"), options))
    message = _sanitize(issue.get("message") or "")
    return f"{prefix}{location}{path}: {message}"


def format_config_issue_lines(
    issues: Iterable[dict], marker: str = "-", opts: Optional[dict] = None
) -> List[str]:
    return [format_config_issue_line(i, marker, opts) for i in issues or []]


def format_config_issue_summary(
    issues: Iterable[dict], opts: Optional[dict] = None
) -> Optional[str]:
    """Build a compact, terminal-safe issue summary for logs."""
    issues_list = list(issues or [])
    if not issues_list:
        return None
    options = opts or {}
    max_issues_raw = options.get("maxIssues", 5)
    try:
        max_issues_candidate = int(max_issues_raw)
    except (TypeError, ValueError):
        max_issues_candidate = 5
    if not (max_issues_candidate == max_issues_candidate):  # NaN check
        max_issues_candidate = 5
    max_issues = max(1, max_issues_candidate)
    visible = issues_list[:max_issues]
    lines = format_config_issue_lines(visible, "", {
        "normalizeRoot": options.get("normalizeRoot", True),
    })
    hidden = len(issues_list) - len(visible)
    if hidden <= 0:
        return "; ".join(lines)
    return f"{'; '.join(lines)}; and {hidden} more"


__all__ = [
    "ConfigValidationIssue",
    "normalize_config_issue_path",
    "normalize_config_issue",
    "normalize_config_issues",
    "format_config_issue_line",
    "format_config_issue_lines",
    "format_config_issue_summary",
]
