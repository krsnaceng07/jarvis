"""jarvis.config.issue_location — config issue path normalization.

OpenClaw parity: mirrors ``openclaw-main/src/config/issue-location.ts``.

Focused minimal port: thin facade that delegates to caller-provided
callables for path segmentation. The Python port focuses on the
``<root>``/blank-path normalization behavior.
"""
from __future__ import annotations

import re
from typing import Any, Optional


#: Matches a numeric path segment like ``[0]``.
_INDEX_RE = re.compile(r"\[\d+\]")


def normalize_issue_location_path(path: Any) -> str:
    """Normalize ``path`` for display: blank -> ``<root>``, trim, replace ``[0]`` with ``[]``.

    Mirrors :func:`normalizeIssueLocationPath`
    (``shared/config/issue-location.ts`).
    """
    if not isinstance(path, str):
        return "<root>"
    trimmed = path.strip()
    if not trimmed:
        return "<root>"
    return _INDEX_RE.sub("[]", trimmed)


def issue_location_segments(path: Any) -> list:
    """Split a path into display segments. Numbers inside brackets are returned as ints.

    Mirrors :func:`issueLocationSegments`
    (``shared/config/issue-location.ts`).
    """
    if not isinstance(path, str) or not path.strip():
        return []
    out: list = []
    for raw in path.replace("[", ".").replace("]", "").split("."):
        if not raw:
            continue
        if raw.isdigit():
            out.append(int(raw))
        else:
            out.append(raw)
    return out


def format_issue_location_path(
    path: Any,
    *,
    source_file: Any = None,
    line: Any = None,
) -> str:
    """Format ``path`` as ``source_file:line — path`` when source/line are present."""
    base = normalize_issue_location_path(path)
    if isinstance(source_file, str) and source_file.strip() and isinstance(line, int) and line > 0:
        return f"{source_file}:{line} — {base}"
    return base


__all__ = [
    "normalize_issue_location_path",
    "issue_location_segments",
    "format_issue_location_path",
]
