"""jarvis.agents.block_chunker — Markdown-safe block chunking and human delay pacing.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-block-chunker.ts`` and
``openclaw-main/src/agents/agent-scope-config.ts`` (humanDelay).

Features:
- Markdown code fence preservation (`find_fence_spans`, `is_inside_fence`).
- `EmbeddedBlockChunker` with min/max bounds and break preferences
  (`paragraph` -> `newline` -> `sentence` -> whitespace -> hard break).
- Code fence auto-close and auto-reopen when forced at `maxChars`.
- `HumanDelayPacer` supporting `off`, `natural` (800-2500ms), and `custom` (`minMs`/`maxMs`).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Callable, Literal, Sequence

BreakPreference = Literal["paragraph", "newline", "sentence"]
HumanDelayMode = Literal["off", "natural", "custom"]


@dataclass(frozen=True, slots=True)
class BlockReplyChunking:
    min_chars: int = 100
    max_chars: int = 1000
    break_preference: BreakPreference | None = "paragraph"
    flush_on_paragraph: bool = False


@dataclass(frozen=True, slots=True)
class FenceSpan:
    start: int
    end: int
    open_line: str
    close_line: str


# Regex matching Markdown code fence lines (e.g. ```python or ~~~)
_FENCE_REGEX = re.compile(r"^([ \t]*)(`{3,}|~{3,})([^\n]*)$", re.MULTILINE)


def parse_fence_spans(text: str) -> list[FenceSpan]:
    """Parse Markdown code fence spans in *text*.

    Returns a list of FenceSpan objects representing code block ranges.
    """
    matches = list(_FENCE_REGEX.finditer(text))
    spans: list[FenceSpan] = []
    i = 0
    while i < len(matches):
        open_match = matches[i]
        open_start = open_match.start()
        open_marker = open_match.group(2)

        # Look for matching closing fence
        j = i + 1
        close_match = None
        while j < len(matches):
            cand = matches[j]
            cand_marker = cand.group(2)
            if cand_marker[0] == open_marker[0] and len(cand_marker) >= len(open_marker):
                close_match = cand
                break
            j += 1

        if close_match:
            close_end = close_match.end()
            spans.append(
                FenceSpan(
                    start=open_start,
                    end=close_end,
                    open_line=open_match.group(0),
                    close_line=close_match.group(0),
                )
            )
            i = j + 1
        else:
            # Unclosed fence spanning to the end of text
            spans.append(
                FenceSpan(
                    start=open_start,
                    end=len(text),
                    open_line=open_match.group(0),
                    close_line=f"{open_match.group(1)}{open_marker}",
                )
            )
            break

    return spans


def is_safe_fence_break(fence_spans: Sequence[FenceSpan], pos: int) -> bool:
    """Return True if *pos* is not inside an active Markdown code fence."""
    for span in fence_spans:
        if span.start < pos < span.end:
            return False
    return True


class EmbeddedBlockChunker:
    """Splits streamed agent output into Markdown-safe message chunks.

    Mirrors ``EmbeddedBlockChunker`` (``embedded-agent-block-chunker.ts``).
    """

    def __init__(self, chunking: BlockReplyChunking | None = None) -> None:
        self.chunking = chunking or BlockReplyChunking()
        self._buffer = ""

    def append(self, text: str) -> None:
        """Add streamed text to the pending buffer."""
        if text:
            self._buffer += text

    def reset(self) -> None:
        """Clear buffered text without emitting."""
        self._buffer = ""

    @property
    def buffered_text(self) -> str:
        return self._buffer

    def has_buffered(self) -> bool:
        return len(self._buffer) > 0

    def _find_break_index(self, text: str, fence_spans: list[FenceSpan], min_chars: int, max_chars: int) -> int:
        """Find the best Markdown-safe split position before *max_chars*."""
        pref = self.chunking.break_preference or "paragraph"

        # Paragraph split (\n\n)
        if pref in ("paragraph", "newline", "sentence"):
            idx = text.rfind("\n\n", 0, max_chars)
            if idx >= min_chars and is_safe_fence_break(fence_spans, idx):
                return idx + 2

        # Newline split (\n)
        if pref in ("newline", "sentence"):
            idx = text.rfind("\n", 0, max_chars)
            if idx >= min_chars and is_safe_fence_break(fence_spans, idx):
                return idx + 1

        # Sentence split ([.!?])
        if pref == "sentence":
            matches = list(re.finditer(r"[.!?](?=\s|$)", text[:max_chars]))
            for m in reversed(matches):
                idx = m.end()
                if idx >= min_chars and is_safe_fence_break(fence_spans, idx):
                    return idx

        # Whitespace split
        idx = text.rfind(" ", 0, max_chars)
        if idx >= min_chars and is_safe_fence_break(fence_spans, idx):
            return idx + 1

        # Fallback to max_chars
        return min(len(text), max_chars)

    def drain(self, *, force: bool, emit: Callable[[str], None]) -> None:
        """Emit safe chunks according to size and Markdown fence constraints.

        Mirrors ``chunker.drain()``.
        """
        min_chars = max(1, self.chunking.min_chars)
        max_chars = max(min_chars, self.chunking.max_chars)

        if len(self._buffer) < min_chars and not force:
            return

        if force and len(self._buffer) <= max_chars:
            if self._buffer.strip():
                emit(self._buffer)
            self._buffer = ""
            return

        source = self._buffer
        fence_spans = parse_fence_spans(source)
        start = 0

        while start < len(source):
            remaining = source[start:]
            if not force and len(remaining) < min_chars:
                break

            if len(remaining) <= max_chars and force:
                emit(remaining)
                start = len(source)
                break

            split_pos = self._find_break_index(remaining, fence_spans, min_chars, max_chars)
            if split_pos <= 0:
                if force:
                    emit(remaining)
                    start = len(source)
                break

            chunk = remaining[:split_pos]
            if chunk.strip():
                emit(chunk)
            start += split_pos

        self._buffer = source[start:]


class HumanDelayPacer:
    """Calculates human-like pauses between block replies.

    Mirrors ``humanDelay`` settings in ``agents.defaults.humanDelay``.
    Modes:
    - ``off``: 0 ms delay.
    - ``natural``: 800 - 2500 ms random delay.
    - ``custom``: min_ms - max_ms random delay.
    """

    def __init__(
        self,
        mode: HumanDelayMode = "off",
        min_ms: int = 800,
        max_ms: int = 2500,
    ) -> None:
        self.mode = mode
        self.min_ms = min_ms
        self.max_ms = max_ms

    def get_delay_seconds(self) -> float:
        """Return the calculated pause in seconds (for asyncio.sleep)."""
        if self.mode == "off":
            return 0.0
        if self.mode == "natural":
            return random.randint(800, 2500) / 1000.0
        # custom
        lo = max(0, self.min_ms)
        hi = max(lo, self.max_ms)
        return random.randint(lo, hi) / 1000.0


__all__ = [
    "BlockReplyChunking",
    "BreakPreference",
    "EmbeddedBlockChunker",
    "FenceSpan",
    "HumanDelayMode",
    "HumanDelayPacer",
    "is_safe_fence_break",
    "parse_fence_spans",
]
