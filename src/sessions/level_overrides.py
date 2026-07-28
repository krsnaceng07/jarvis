"""Session level overrides — per-session verbose + trace level parsing.

Mirrors OpenClaw's ``extensions/sessions/level-overrides.ts``:
``parse_verbose_override`` + ``apply_verbose_override`` +
``parse_trace_override`` + ``apply_trace_override``, all
using a tri-state result (``undefined`` = no change,
``null`` = clear the override, level = set the override).

The Python port inlines the verbose/trace level
normalizers (they're tiny — single-line switches) so we
don't need to pull in the entire ``auto-reply/thinking``
surface. The semantics match the TS source exactly:

- ``VerboseLevel`` = ``"on" | "off" | "full"`` (case-insensitive)
- ``TraceLevel`` = ``"on" | "off" | "raw"`` (case-insensitive)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional, Union

# ── Verbose level ────────────────────────────────────────────────────


VerboseLevel = Literal["on", "off", "full"]

_VERBOSE_LEVEL_VALUES: frozenset[str] = frozenset({"on", "off", "full"})


def normalize_verbose_level(value: Any) -> Optional[VerboseLevel]:
    """Normalize a user-supplied verbose level string to the canonical form.

    Mirrors ``normalizeVerboseLevel`` in
    ``extensions/auto-reply/thinking.ts``. Returns ``None``
    for non-strings or unrecognized values.
    """
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in _VERBOSE_LEVEL_VALUES:
        return normalized  # type: ignore[return-value]
    return None


# ── Trace level ──────────────────────────────────────────────────────


TraceLevel = Literal["on", "off", "raw"]

_TRACE_LEVEL_VALUES: frozenset[str] = frozenset({"on", "off", "raw"})


def normalize_trace_level(value: Any) -> Optional[TraceLevel]:
    """Normalize a user-supplied trace level string to the canonical form.

    Mirrors ``normalizeTraceLevel`` in
    ``extensions/auto-reply/thinking.ts``.
    """
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in _TRACE_LEVEL_VALUES:
        return normalized  # type: ignore[return-value]
    return None


# ── Parse + apply helpers ───────────────────────────────────────────


_INVALID_VERBOSE_LEVEL_ERROR = 'invalid verboseLevel (use "on"|"off"|"full")'
_INVALID_TRACE_LEVEL_ERROR = 'invalid traceLevel (use "on"|"off"|"raw")'


@dataclass(frozen=True, slots=True)
class ParsedVerboseOverride:
    """Result of ``parse_verbose_override`` — tri-state (set | clear | no-op)."""

    ok: bool
    value: Optional[VerboseLevel] = None
    # Tri-state: ``None`` = no change, ``""`` = clear, level = set
    error: Optional[str] = None


def parse_verbose_override(raw: Any) -> ParsedVerboseOverride:
    """Parse a user-supplied verbose override.

    Returns a tri-state result:
    - ``raw is None`` → ``{ok: True, value: None}`` (clear the override)
    - ``raw is undefined`` → ``{ok: True, value: None}`` (no change —
      note: the TS source uses ``undefined`` for the same sentinel;
      Python collapses ``undefined`` to ``None`` for input only)
    - ``raw`` is a valid verbose level → ``{ok: True, value: <level>}``
    - otherwise → ``{ok: False, error: ...}``

    Mirrors the TS ``parseVerboseOverride`` (the
    ``undefined`` sentinel is the same as the TS source's
    "no change" branch).
    """
    if raw is None:
        return ParsedVerboseOverride(ok=True, value=None)
    if not isinstance(raw, str):
        return ParsedVerboseOverride(ok=False, error=_INVALID_VERBOSE_LEVEL_ERROR)
    normalized = normalize_verbose_level(raw)
    if normalized is None:
        return ParsedVerboseOverride(ok=False, error=_INVALID_VERBOSE_LEVEL_ERROR)
    return ParsedVerboseOverride(ok=True, value=normalized)


def apply_verbose_override(
    entry: dict[str, Any], level: Optional[VerboseLevel]
) -> None:
    """Mutate ``entry`` with the parsed verbose override.

    Mirrors the TS ``applyVerboseOverride``:
    - ``level is None`` → no change (or clear, depending on
      how the caller chose the sentinel)
    - ``level == ""`` → clear the saved override
    - level value → set the override

    The Python port uses an empty string to distinguish
    "clear" from "no change" (since ``None`` is the
    "no change" sentinel).
    """
    if level is None:
        return
    if level == "":  # type: ignore[comparison-overlap]
        entry.pop("verboseLevel", None)
        return
    entry["verboseLevel"] = level


@dataclass(frozen=True, slots=True)
class ParsedTraceOverride:
    """Result of ``parse_trace_override`` — tri-state (set | clear | no-op)."""

    ok: bool
    value: Optional[TraceLevel] = None
    error: Optional[str] = None


def parse_trace_override(raw: Any) -> ParsedTraceOverride:
    """Parse a user-supplied trace override. Mirrors the TS ``parseTraceOverride``."""
    if raw is None:
        return ParsedTraceOverride(ok=True, value=None)
    if not isinstance(raw, str):
        return ParsedTraceOverride(ok=False, error=_INVALID_TRACE_LEVEL_ERROR)
    normalized = normalize_trace_level(raw)
    if normalized is None:
        return ParsedTraceOverride(ok=False, error=_INVALID_TRACE_LEVEL_ERROR)
    return ParsedTraceOverride(ok=True, value=normalized)


def apply_trace_override(entry: dict[str, Any], level: Optional[TraceLevel]) -> None:
    """Mutate ``entry`` with the parsed trace override. Mirrors ``applyTraceOverride``."""
    if level is None:
        return
    if level == "":  # type: ignore[comparison-overlap]
        entry.pop("traceLevel", None)
        return
    entry["traceLevel"] = level


__all__ = [
    "ParsedTraceOverride",
    "ParsedVerboseOverride",
    "TraceLevel",
    "VerboseLevel",
    "apply_trace_override",
    "apply_verbose_override",
    "normalize_trace_level",
    "normalize_verbose_level",
    "parse_trace_override",
    "parse_verbose_override",
]
