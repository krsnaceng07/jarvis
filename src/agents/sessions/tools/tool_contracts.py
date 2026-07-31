"""jarvis.agents.sessions.tools.tool_contracts — shared built-in tool input/detail contracts.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/tool-contracts.ts``.

Phase 6.10a — shared tool contracts.

Keeps tool factories, renderers, and callers
aligned on typed payload + metadata shapes
for every built-in tool. Every Input/Detail
contract that the built-in tools (read, write,
edit, bash, find, grep, ls) consume or
produce lives here.

Adaptations
-----------
- The OpenClaw source uses TS ``interface``
  + ``type`` / ``function`` aliases. The
  Python port uses :class:`TypedDict` for
  the data-only shapes + plain ``def`` for
  the small helper functions.
- The OpenClaw source's ``Edit`` import
  from ``./edit-diff.js`` is replaced with
  a re-export from the Phase 6.10c
  ``edit_diff`` module (``Edit = dict``
  re-exported as ``EditOp`` in this package).
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict


# ============================================================================
# Re-exports (Phase 6.10c lands the real shapes)
# ============================================================================


#: Edit operation shape (Phase 6.10c).
#: Re-exported from :mod:`edit_diff` for the
#: ``EditToolInput.edits`` field type.
Edit = dict  # see ``EditOp`` re-export in :mod:`__init__`


# ============================================================================
# Truncation re-export
# ============================================================================


#: Truncation result metadata. Mirrors
#: ``TruncationResult`` (truncate.ts:7-30).
#: The Python port re-exports
#: :class:`jarvis_agent.truncate.TruncationResult`
#: so the tool layer uses one byte/line
#: truncation contract end-to-end.
TruncationResult = Any  # jarvis_agent.truncate.TruncationResult


# ============================================================================
# Bash
# ============================================================================


class BashToolInput(TypedDict, total=False):
    command: str
    timeout: int


class BashToolDetails(TypedDict, total=False):
    truncation: Optional[TruncationResult]
    fullOutputPath: Optional[str]


def format_full_output_footer(path: str) -> str:
    """Build the canonical "Full output: <path>"
    footer. Mirrors ``formatFullOutputFooter``
    (``tool-contracts.ts:19-21``)."""
    return f"Full output: {path}"


# ============================================================================
# Edit
# ============================================================================


class EditToolInput(TypedDict, total=False):
    path: str
    edits: list  # list[Edit]


#: ``EditToolDetails`` is a discriminated
#: union: ``{changed: false}`` or
#: ``{changed: true, diff, patch,
#: firstChangedLine?}``. Mirrors
#: ``EditToolDetails``
#: (``tool-contracts.ts:28-40``). The
#: Python port uses ``dict`` (no runtime
#: discriminator).
EditToolDetails = dict


# ============================================================================
# Find
# ============================================================================


class FindToolInput(TypedDict, total=False):
    pattern: str
    path: Optional[str]
    limit: Optional[int]


class FindToolDetails(TypedDict, total=False):
    truncation: Optional[TruncationResult]
    resultLimitReached: Optional[int]


# ============================================================================
# Grep
# ============================================================================


class GrepToolInput(TypedDict, total=False):
    pattern: str
    path: Optional[str]
    glob: Optional[str]
    ignoreCase: Optional[bool]
    literal: Optional[bool]
    context: Optional[int]
    limit: Optional[int]


class GrepToolDetails(TypedDict, total=False):
    truncation: Optional[TruncationResult]
    matchLimitReached: Optional[int]
    linesTruncated: Optional[bool]


# ============================================================================
# Ls
# ============================================================================


class LsToolInput(TypedDict, total=False):
    path: Optional[str]
    limit: Optional[int]


class LsToolDetails(TypedDict, total=False):
    truncation: Optional[TruncationResult]
    entryLimitReached: Optional[int]


# ============================================================================
# Read
# ============================================================================


class ReadToolInput(TypedDict, total=False):
    path: str
    offset: Optional[int]
    limit: Optional[int]


#: ``ReadToolTruncationDetails`` = ``TruncationResult`` minus ``content``.
#: Mirrors ``ReadToolTruncationDetails``
#: (``tool-contracts.ts:85``). The Python
#: port uses ``dict`` (the OpenClaw source's
#: ``Omit<TruncationResult, "content">`` is
#: a structural type, not a runtime class).
ReadToolTruncationDetails = dict


#: ``ReadToolDetails`` is a discriminated
#: union over the read result kind. Mirrors
#: ``ReadToolDetails``
#: (``tool-contracts.ts:87-100``). The
#: Python port uses ``dict`` (no runtime
#: discriminator; callers branch on
#: ``details["kind"]``).
ReadToolDetails = dict


# ============================================================================
# Write
# ============================================================================


class WriteToolInput(TypedDict, total=False):
    path: str
    content: str


__all__ = [
    "BashToolDetails",
    "BashToolInput",
    "Edit",
    "EditToolDetails",
    "EditToolInput",
    "FindToolDetails",
    "FindToolInput",
    "GrepToolDetails",
    "GrepToolInput",
    "LsToolDetails",
    "LsToolInput",
    "ReadToolDetails",
    "ReadToolInput",
    "ReadToolTruncationDetails",
    "TruncationResult",
    "WriteToolInput",
    "format_full_output_footer",
]
