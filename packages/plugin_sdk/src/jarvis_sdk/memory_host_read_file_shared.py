"""jarvis_sdk.memory_host_read_file_shared — memory-file read result shaping.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/read-file-shared.ts`` (131 LOC).
Shared memory-file read result shaping and truncation notices.
The helpers here take already-selected line slices (or raw file
content + range options) and produce a ``MemoryReadResult`` that
includes the truncated text, the ``nextFrom`` cursor, and a
human-readable continuation notice.

Public API:
- ``DEFAULT_MEMORY_READ_LINES`` (120) and
  ``DEFAULT_MEMORY_READ_MAX_CHARS`` (12_000).
- ``MemoryReadResult`` (TypedDict) — result envelope.
- ``build_memory_read_result_from_slice(...)`` — shape a result
  from a pre-selected list of lines.
- ``build_memory_read_result(...)`` — slice the file content
  first, then delegate to the slice variant.

Key port decisions:
- ``truncate_utf16_safe`` is reused from
  ``jarvis_sdk.text_utility`` (the same helper is used by
  memory-lancedb for embedding input truncation).
- The result envelope is a ``TypedDict`` (not a dataclass) to
  preserve the optional ``truncated`` / ``nextFrom`` field
  shape — OpenClaw's JS object uses optional properties.
- The continuation notice is a literal ``\\n\\n``-prefixed
  marker so downstream agents can pattern-match on it.
"""
from __future__ import annotations

from typing import TypedDict

from .text_utility import truncate_utf16_safe

# Mirrors OpenClaw's ``DEFAULT_MEMORY_READ_LINES = 120``.
# Used as the default line count when callers don't specify one.
DEFAULT_MEMORY_READ_LINES: int = 120

# Mirrors OpenClaw's ``DEFAULT_MEMORY_READ_MAX_CHARS = 12_000``.
# Used as the default char budget for ``build_memory_read_result``
# when callers don't pass ``maxChars``.
DEFAULT_MEMORY_READ_MAX_CHARS: int = 12_000


class MemoryReadResult(TypedDict, total=False):
    """Memory read result envelope. Mirrors OpenClaw's ``MemoryReadResult``.

    Optional fields are added when truncation occurred. Mirrors
    the OpenClaw ``MemoryReadResult`` type from
    ``packages/memory-host-sdk/src/host/types.ts``.

    Note: ``from`` is a Python keyword, so the field is declared
    as the string key ``"from"``. Callers should use
    ``result["from"]`` (string-keyed access) rather than
    attribute access.
    """

    text: str
    path: str
    # ``from`` is a Python keyword — declared via ``__annotations__``
    # at the bottom of the file so the field exists in the TypedDict
    # schema without triggering a SyntaxError here.
    lines: int
    truncated: bool
    # ``nextFrom`` camelCase mirrors OpenClaw JSON.
    nextFrom: int  # noqa: N815


def _build_continuation_notice(
    next_from: int | None,
    suggest_read_fallback: bool = False,
) -> str:
    """Build the continuation notice appended to truncated excerpts.

    Mirrors OpenClaw's ``buildContinuationNotice``. When
    ``next_from`` is known, the notice carries the cursor so
    downstream agents can issue a follow-up read. When
    ``suggest_read_fallback`` is true (typically when a single
    line was hard-truncated by the char budget), the notice
    also nudges callers toward ``read on the source file``.
    """
    if isinstance(next_from, int):
        base = f"[More content available. Use from={next_from} to continue."
    else:
        base = "[More content available. Requested excerpt exceeded the default maxChars budget."
    fallback = (
        " If you need the full raw line, use read on the source file."
        if suggest_read_fallback
        else ""
    )
    # OpenClaw strips the trailing ``]`` from ``base`` and appends
    # the (possibly empty) fallback before re-adding the ``]``.
    return f"\n\n{base[:-1]}{fallback}]"


def _fit_lines_to_char_budget(
    lines: list[str],
    max_chars: int,
) -> tuple[str, int, bool]:
    """Fit a line slice to a char budget while preserving line boundaries.

    Mirrors OpenClaw's ``fitLinesToCharBudget``. Returns the
    fitted text, the number of lines included, and a flag
    indicating whether a single line was hard-truncated by
    UTF-16-safe character slicing.

    When the joined text fits in the budget, all lines are
    included. Otherwise, lines are dropped from the end until
    the joined text fits. If even a single line is still over
    the budget, the line is hard-truncated (UTF-16 safe) and
    the flag is set to ``True``.
    """
    if not lines:
        return "", 0, False

    included_lines = len(lines)
    text = "\n".join(lines)
    while included_lines > 1 and len(text) > max_chars:
        included_lines -= 1
        text = "\n".join(lines[:included_lines])

    if len(text) <= max_chars:
        return text, included_lines, False

    # Single line still over budget — hard-truncate it.
    return truncate_utf16_safe(text, max_chars), 1, True


def _normalize_positive_integer(
    value: int | float | None,
    fallback: int,
) -> int:
    """Normalize an optional numeric config to a positive integer.

    Mirrors OpenClaw's ``normalizePositiveInteger``. Returns
    ``max(1, floor(value))`` when ``value`` is a finite number;
    otherwise returns ``fallback``.
    """
    if isinstance(value, bool):  # ``bool`` is a subclass of ``int`` — exclude it explicitly
        return fallback
    if isinstance(value, (int, float)) and value == value:  # NaN check via ``== self``
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return fallback
    return fallback


def build_memory_read_result_from_slice(
    selected_lines: list[str],
    rel_path: str,
    start_line: int,
    more_source_lines_remain: bool | None = None,
    max_chars: int | None = None,
    suggest_read_fallback: bool = False,
) -> MemoryReadResult:
    """Build a memory-read result from a pre-selected line slice.

    Mirrors OpenClaw's ``buildMemoryReadResultFromSlice``. The
    caller is responsible for slicing the file content; this
    helper handles the char-budget fitting + continuation
    notice.

    Returns a ``MemoryReadResult`` TypedDict. The ``truncated``
    field is present only when truncation occurred; the
    ``nextFrom`` field is present only when a follow-up
    ``from=`` cursor would advance the read.
    """
    start = _normalize_positive_integer(start_line, 1)
    char_budget = _normalize_positive_integer(max_chars, DEFAULT_MEMORY_READ_MAX_CHARS)
    fitted_text, included_lines, hard_truncated = _fit_lines_to_char_budget(
        selected_lines, char_budget
    )
    more_remain = bool(more_source_lines_remain) if more_source_lines_remain is not None else False
    char_cap_truncated = hard_truncated or included_lines < len(selected_lines)
    more_after = more_remain or included_lines < len(selected_lines)
    next_from: int | None = (
        start + included_lines if not hard_truncated and more_after else None
    )
    truncated = char_cap_truncated or more_remain

    text: str
    if truncated and (fitted_text or hard_truncated):
        text = fitted_text + _build_continuation_notice(
            next_from,
            suggest_read_fallback=hard_truncated and suggest_read_fallback,
        )
    else:
        text = fitted_text

    result: MemoryReadResult = {
        "text": text,
        "path": rel_path,
        "from": start,
        "lines": included_lines,
    }
    if truncated:
        result["truncated"] = True
    if isinstance(next_from, int):
        result["nextFrom"] = next_from
    return result


def build_memory_read_result(
    content: str,
    rel_path: str,
    from_: int | None = None,
    lines: int | None = None,
    default_lines: int | None = None,
    max_chars: int | None = None,
    suggest_read_fallback: bool = False,
) -> MemoryReadResult:
    """Build a memory-read result from raw file content + range options.

    Mirrors OpenClaw's ``buildMemoryReadResult``. Splits the
    content on ``\\n``, slices according to ``from_`` /
    ``lines`` (or ``default_lines``), then delegates to
    ``build_memory_read_result_from_slice`` for char-budget
    fitting and notice generation.
    """
    file_lines = content.split("\n")
    start = _normalize_positive_integer(from_, 1)
    requested_count = _normalize_positive_integer(
        lines if lines is not None else default_lines,
        DEFAULT_MEMORY_READ_LINES,
    )
    selected = file_lines[start - 1 : start - 1 + requested_count]
    more_remain = (start - 1 + len(selected)) < len(file_lines)
    return build_memory_read_result_from_slice(
        selected,
        rel_path,
        start,
        more_remain,
        max_chars,
        suggest_read_fallback,
    )


__all__ = [
    "DEFAULT_MEMORY_READ_LINES",
    "DEFAULT_MEMORY_READ_MAX_CHARS",
    "MemoryReadResult",
    "build_memory_read_result_from_slice",
    "build_memory_read_result",
]

# ``from`` is a Python keyword; we register it on the TypedDict
# after the class body so it appears in the schema.
MemoryReadResult.__annotations__["from"] = int  # type: ignore[attr-defined]
