"""Parser limits and allowlist options for plain-text tool-call repair.

OpenClaw parity: ``packages/tool-call-repair/src/contracts.ts``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PlainTextToolCallParseOptions:
    """Parser limits and allowlist options."""

    allowed_tool_names: Iterable[str] | None = None
    max_payload_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class NormalizedParseOptions:
    """Parse options with the allowlist materialized to a set (or ``None``)."""

    allowed_tool_names: frozenset[str] | None = None
    max_payload_bytes: int | None = None


def normalize_parse_options(
    options: PlainTextToolCallParseOptions | None,
) -> NormalizedParseOptions | None:
    """Materialize the allowlist iterable to a set, mirroring TS normalization."""
    if options is None:
        return None
    return NormalizedParseOptions(
        allowed_tool_names=(
            frozenset(options.allowed_tool_names)
            if options.allowed_tool_names is not None
            else None
        ),
        max_payload_bytes=options.max_payload_bytes,
    )


class PlainTextToolCallNameMatcher(Protocol):
    """Structural matcher for candidate tool names."""

    def has_exact_name(self, name: str) -> bool: ...
    def has_name_prefix(self, prefix: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class PlainTextToolCallProtectedRange:
    """Source range that must remain literal user-visible text."""

    start: int = 0
    end: int = 0


#: Resolves protected ranges against the exact text about to be scanned.
PlainTextToolCallProtectedRangeResolver = Callable[[str], list["PlainTextToolCallProtectedRange"]]


def is_offset_in_protected_ranges(
    offset: int, ranges: list[PlainTextToolCallProtectedRange]
) -> bool:
    """Return True when ``offset`` sits inside any protected range."""
    return any(item.start <= offset < item.end for item in ranges)


__all__ = [
    "NormalizedParseOptions",
    "PlainTextToolCallNameMatcher",
    "PlainTextToolCallParseOptions",
    "PlainTextToolCallProtectedRange",
    "PlainTextToolCallProtectedRangeResolver",
    "is_offset_in_protected_ranges",
    "normalize_parse_options",
]
