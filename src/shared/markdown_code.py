"""jarvis.shared.markdown_code — Markdown inline code and fenced blocks.

OpenClaw parity: mirrors ``openclaw-main/src/shared/markdown-code.ts``.
"""
from __future__ import annotations

from typing import Optional


def _longest_backtick_run(value: str) -> int:
    longest = 0
    current = 0
    for ch in value:
        if ch == "`":
            current += 1
            if current > longest:
                longest = current
            continue
        current = 0
    return longest


def format_inline_code_span(value: str) -> str:
    """Wrap text in an inline code span whose delimiter exceeds any run inside.

    Mirrors :func:`formatInlineCodeSpan` (``shared/markdown-code.ts``).
    """
    delimiter = "`" * (_longest_backtick_run(value) + 1)
    padding = " " if (value.startswith("`") or value.endswith("`") or "\n" in value) else ""
    return f"{delimiter}{padding}{value}{padding}{delimiter}"


def format_fenced_code_block(text: str, language: Optional[str] = None) -> str:
    """Wrap text in a fenced code block whose fence exceeds any backtick run.

    Mirrors :func:`formatFencedCodeBlock` (``shared/markdown-code.ts``).
    """
    fence = "`" * max(3, _longest_backtick_run(text) + 1)
    return f"{fence}{language or ''}\n{text}\n{fence}"


__all__ = ["format_inline_code_span", "format_fenced_code_block"]
