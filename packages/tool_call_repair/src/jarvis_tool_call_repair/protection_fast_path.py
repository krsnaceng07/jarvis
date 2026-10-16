"""Incremental Markdown-protection fast path for the stream normalizer.

OpenClaw parity:
``packages/tool-call-repair/src/protection-fast-path.ts``.
The normalizer must know whether a candidate tool call sits inside a
code region before scrubbing it. A full Markdown parse of the whole
accumulated response on every candidate delta is quadratic, so this
tracker carries block state forward as text is appended.

Safety contract: conservative fast path. It answers only when the
verdict is provable from fence state alone and declines (``None``)
for every shape it does not model (inline code spans, indented code,
block quotes, lists). Callers must fall back to the authoritative
full parse on decline, so protection semantics stay identical.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

_FENCE_OPEN_RE = re.compile(r" {0,3}(`{3,}|~{3,})")
#: Blank means spaces and tabs only; Unicode spaces do not end a block.
_BLANK_LINE_RE = re.compile(r"^[ \t]*$")
#: A CR that does not begin a CRLF pair (bare CR ends a line for scanners
#: but this tracker splits on LF only, so it must decline).
_BARE_CARRIAGE_RETURN_RE = re.compile(r"\r(?!\n)")
#: A fence-length delimiter run outside a fence, unclassifiable here.
_UNCLASSIFIED_FENCE_RE = re.compile(r"`{3,}|~{3,}")
#: Line starts that make indentation/delimiters structural (unmodeled).
_UNMODELED_BLOCK_START_RE = re.compile(
    r"^(?: {0,3}(?:>|[-*+](?:\s|$)|\d{1,9}[.)](?:\s|$))| {4,}| *\t)"
)
_CLOSE_FENCE_RE = re.compile(r" {0,3}(`{3,}|~{3,})[ \t]*$")


@dataclass
class ProtectionScanState:
    """Carried block state at a position in the accumulated response."""

    fence_char: str | None = None
    fence_length: int = 0
    # Set when the paragraph holds an unmodeled construct; cleared on a
    # blank line because none of those constructs span one.
    paragraph_ambiguous: bool = False
    # Set when fence parity is permanently unknown; never clears.
    structural_unknown: bool = False
    # Trailing partial line; block structure is decidable on whole lines only.
    partial_line: str = ""


def create_protection_scan_state() -> ProtectionScanState:
    """Create a fresh carried scan state."""
    return ProtectionScanState()


def clone_protection_scan_state(state: ProtectionScanState) -> ProtectionScanState:
    """Copy carried scan state (the resolver must not mutate the caller's)."""
    return ProtectionScanState(
        fence_char=state.fence_char,
        fence_length=state.fence_length,
        paragraph_ambiguous=state.paragraph_ambiguous,
        structural_unknown=state.structural_unknown,
        partial_line=state.partial_line,
    )


def _apply_line(state: ProtectionScanState, line: str) -> None:
    if state.structural_unknown:
        return
    if state.fence_char is not None:
        # Inside a fence only a matching closing run is structural. Only
        # spaces/tabs may follow it: `\s` would also match U+00A0, which
        # does NOT close a fence, and misreading it would scrub fenced text.
        close = _CLOSE_FENCE_RE.match(line)
        run = close.group(1) if close else None
        if run and run[0] == state.fence_char and len(run) >= state.fence_length:
            state.fence_char = None
            state.fence_length = 0
        return
    if _BLANK_LINE_RE.match(line):
        state.paragraph_ambiguous = False
        return
    fence_open = _FENCE_OPEN_RE.match(line)
    marker = fence_open.group(1) if fence_open else None
    if marker:
        # Only track fences opening at column 0 in unambiguous context.
        # A backtick fence whose info string holds a backtick is not a
        # fence at all; tilde fences allow backticks.
        info_string = line[len(fence_open.group(0)) :] if fence_open else ""
        if (
            state.paragraph_ambiguous
            or (fence_open is not None and len(fence_open.group(0)) != len(marker))
            or (marker[0] == "`" and "`" in info_string)
        ):
            state.structural_unknown = True
            return
        state.fence_char = "~" if marker[0] == "~" else "`"
        state.fence_length = len(marker)
        return
    if _UNCLASSIFIED_FENCE_RE.search(line):
        state.structural_unknown = True
        return
    if "`" in line or _UNMODELED_BLOCK_START_RE.match(line):
        state.paragraph_ambiguous = True


def advance_protection_scan_state(state: ProtectionScanState, text: str) -> None:
    """Feed appended visible text into the carried state."""
    if not text:
        return
    if _BARE_CARRIAGE_RETURN_RE.search(text):
        state.structural_unknown = True
        return
    # `partial_line` never holds a newline, so a line completes here only
    # when `text` itself holds one. Searching `text` alone (instead of the
    # concatenation) keeps a long newline-free stream linear across calls.
    newline = text.find("\n")
    if newline == -1:
        state.partial_line += text
        return
    line = (state.partial_line + text[:newline]).removesuffix("\r")
    _apply_line(state, line)
    cursor = newline + 1
    newline = text.find("\n", cursor)
    while newline != -1:
        line = text[cursor:newline].removesuffix("\r")
        _apply_line(state, line)
        cursor = newline + 1
        newline = text.find("\n", cursor)
    state.partial_line = text[cursor:]


def resolve_protection_fast_path(
    carried: ProtectionScanState, incoming: str
) -> Callable[[int], bool] | None:
    """Decide protection for candidate offsets inside ``incoming``.

    Returns ``None`` when the answer is not provable from fence state
    alone (caller must run the authoritative full parse). Offsets are
    reported relative to ``incoming``; a carried partial line began
    before it. Callers query at non-decreasing offsets in one
    left-to-right scan, so lookup stays linear overall.
    """
    if carried.paragraph_ambiguous or carried.structural_unknown:
        return None
    if _BARE_CARRIAGE_RETURN_RE.search(incoming):
        return None
    # Walk `incoming` once on a copy; the caller advances the real state
    # separately, so this must not mutate it.
    state = clone_protection_scan_state(carried)
    line_starts: list[tuple[int, bool]] = []
    index = 0
    line_start = 0
    while True:
        if index >= len(incoming) and not state.partial_line:
            # Nothing follows the final newline; stop instead of treating
            # the empty tail as an unfinished line that forces a parse.
            break
        newline = incoming.find("\n", index)
        complete = newline != -1
        line = (
            f"{state.partial_line}{incoming[index:] if not complete else incoming[index:newline]}"
        ).removesuffix("\r")
        line_start_absolute = line_start - len(state.partial_line)
        if state.fence_char is not None:
            # Fenced content and delimiter lines sit inside the code region.
            line_starts.append((line_start_absolute, True))
        elif not complete:
            # Outside a fence an unfinished line could still open one or be
            # indented/inline code. Yield to the authoritative parse.
            return None
        else:
            probe = clone_protection_scan_state(state)
            _apply_line(probe, line)
            if probe.paragraph_ambiguous or probe.structural_unknown:
                return None
            opened = _FENCE_OPEN_RE.match(line) if probe.fence_char else None
            marker = opened.group(1) if opened is not None else None
            if opened is not None and marker:
                # The region starts at the delimiter run, so an indented
                # fence leaves its own leading whitespace outside it.
                line_starts.append((line_start_absolute, False))
                line_starts.append(
                    (line_start_absolute + (len(opened.group(0)) - len(marker)), True)
                )
            else:
                line_starts.append((line_start_absolute, False))
        if not complete:
            break
        _apply_line(state, line)
        if state.paragraph_ambiguous or state.structural_unknown:
            return None
        state.partial_line = ""
        index = newline + 1
        line_start = index
        if index > len(incoming):
            break
    cursor = -1
    protected = False

    def is_protected(offset: int) -> bool:
        nonlocal cursor, protected
        # Candidate offsets sit at a line start; the nearest preceding
        # start owns the verdict.
        while cursor + 1 < len(line_starts):
            following = line_starts[cursor + 1]
            if following[0] > offset:
                break
            cursor += 1
            protected = following[1]
        return protected

    return is_protected


__all__ = [
    "ProtectionScanState",
    "advance_protection_scan_state",
    "clone_protection_scan_state",
    "create_protection_scan_state",
    "resolve_protection_fast_path",
]
