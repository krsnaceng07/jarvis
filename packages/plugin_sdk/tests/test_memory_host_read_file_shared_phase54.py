"""Tests for memory_host_read_file_shared — mirrors host/read-file-shared.ts."""

from __future__ import annotations

import sys
from pathlib import Path

# Make the SDK importable when running this file in isolation.
_PKG_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PKG_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from jarvis_sdk.memory_host_read_file_shared import (  # noqa: E402
    DEFAULT_MEMORY_READ_LINES,
    DEFAULT_MEMORY_READ_MAX_CHARS,
    build_memory_read_result,
    build_memory_read_result_from_slice,
)


# ── Constants ───────────────────────────────────────────────────────


def test_default_lines_constant() -> None:
    """DEFAULT_MEMORY_READ_LINES matches OpenClaw (120)."""
    assert DEFAULT_MEMORY_READ_LINES == 120


def test_default_max_chars_constant() -> None:
    """DEFAULT_MEMORY_READ_MAX_CHARS matches OpenClaw (12_000)."""
    assert DEFAULT_MEMORY_READ_MAX_CHARS == 12_000


# ── build_memory_read_result_from_slice ─────────────────────────────


def test_from_slice_empty_lines() -> None:
    """Empty input yields an empty result with includedLines=0."""
    result = build_memory_read_result_from_slice(
        [], "memory/note.md", start_line=1, more_source_lines_remain=False
    )
    assert result.get("text") == ""
    assert result.get("lines") == 0
    assert result.get("truncated") is None
    assert result.get("nextFrom") is None


def test_from_slice_no_truncation() -> None:
    """A short slice that fits the budget is returned verbatim."""
    result = build_memory_read_result_from_slice(
        ["a", "b", "c"], "memory/note.md", start_line=1, more_source_lines_remain=False
    )
    assert result.get("text") == "a\nb\nc"
    assert result.get("lines") == 3
    assert result.get("truncated") is None
    assert result.get("nextFrom") is None


def test_from_slice_with_next_cursor() -> None:
    """When more source lines remain, ``nextFrom`` is set."""
    result = build_memory_read_result_from_slice(
        ["a", "b"], "memory/note.md", start_line=1, more_source_lines_remain=True
    )
    assert result.get("truncated") is True
    assert result.get("nextFrom") == 3  # 1 + 2
    # Continuation notice includes the cursor.
    assert "from=3" in (result.get("text") or "")


def test_from_slice_char_budget_truncation() -> None:
    """When the joined text exceeds the budget, lines are dropped."""
    lines = ["x" * 100, "y" * 100, "z" * 100]
    result = build_memory_read_result_from_slice(
        lines, "memory/note.md", start_line=1, more_source_lines_remain=False, max_chars=150
    )
    # The first line (100 chars) fits in 150 by itself, so we drop
    # the other two. Since lines were dropped, ``truncated`` is set
    # and a ``nextFrom`` cursor is emitted (no hard-truncation).
    assert result.get("lines") == 1
    assert result.get("truncated") is True
    assert result.get("nextFrom") == 2  # start=1, included=1, more=dropped lines


def test_from_slice_hard_truncates_single_line() -> None:
    """A single line over the budget is hard-truncated."""
    result = build_memory_read_result_from_slice(
        ["a" * 1000], "memory/note.md", start_line=1, more_source_lines_remain=False, max_chars=10
    )
    assert result.get("lines") == 1
    assert result.get("truncated") is True
    # The text should be <= max_chars (plus continuation notice).
    assert len((result.get("text") or "").split("\n\n")[0]) <= 10


def test_from_slice_suggest_read_fallback_appended() -> None:
    """When a single line is hard-truncated and suggest_read_fallback
    is set, the notice nudges callers to use the read fallback."""
    result = build_memory_read_result_from_slice(
        ["a" * 1000], "memory/note.md", start_line=1, max_chars=10, suggest_read_fallback=True
    )
    assert "read on the source file" in (result.get("text") or "")


def test_from_slice_no_suggest_fallback_when_not_hard_truncated() -> None:
    """The suggest_read_fallback flag is ignored unless hard-truncation
    happened on a single line."""
    result = build_memory_read_result_from_slice(
        ["a", "b", "c"],
        "memory/note.md",
        start_line=1,
        more_source_lines_remain=True,
        max_chars=100,
        suggest_read_fallback=True,
    )
    # No "read on the source file" since the truncation is from the
    # line-drop path, not the hard-truncate path.
    assert "read on the source file" not in (result.get("text") or "")


def test_from_slice_more_remain_without_truncation_yields_truncated_flag() -> None:
    """When ``more_source_lines_remain`` is True, the result is
    marked ``truncated`` even if the text fits the budget."""
    result = build_memory_read_result_from_slice(
        ["a", "b"], "memory/note.md", start_line=1, more_source_lines_remain=True, max_chars=100
    )
    assert result.get("truncated") is True
    assert result.get("nextFrom") == 3


def test_from_slice_path_propagates() -> None:
    """The ``path`` field echoes the relPath input."""
    result = build_memory_read_result_from_slice(
        ["a"], "memory/sub/note.md", start_line=1, more_source_lines_remain=False
    )
    assert result.get("path") == "memory/sub/note.md"


def test_from_slice_start_line_normalized() -> None:
    """Non-positive start_line is normalized to 1."""
    result = build_memory_read_result_from_slice(
        ["a", "b", "c"], "memory/note.md", start_line=0, more_source_lines_remain=True
    )
    assert result.get("from") == 1
    assert result.get("nextFrom") == 4  # 1 + 3


def test_from_slice_start_line_negative_normalized() -> None:
    """Negative start_line is normalized to 1."""
    result = build_memory_read_result_from_slice(
        ["a"], "memory/note.md", start_line=-5, more_source_lines_remain=False
    )
    assert result.get("from") == 1


def test_from_slice_start_line_nan_falls_back() -> None:
    """A non-numeric start_line falls back to 1."""
    result = build_memory_read_result_from_slice(
        ["a"],
        "memory/note.md",
        start_line="not a number",  # type: ignore[arg-type]
    )
    assert result.get("from") == 1


# ── build_memory_read_result ────────────────────────────────────────


def test_build_basic() -> None:
    """Default range reads the first 120 lines from line 1."""
    content = "\n".join(str(i) for i in range(200))
    result = build_memory_read_result(content, "memory/note.md")
    assert result.get("from") == 1
    assert result.get("lines") == 120
    assert result.get("path") == "memory/note.md"
    assert "truncated" in result
    assert result.get("nextFrom") == 121


def test_build_with_from_and_lines() -> None:
    """Custom range reads the requested slice; ``more_source_lines_remain``
    is True whenever the slice doesn't reach EOF, so the result is
    marked ``truncated`` and carries a ``nextFrom`` cursor."""
    content = "\n".join(str(i) for i in range(100))
    result = build_memory_read_result(content, "memory/note.md", from_=10, lines=5)
    assert result.get("from") == 10
    assert result.get("lines") == 5
    # The 5 lines from 10-14 don't cover the full 100-line file,
    # so more lines remain — the result is ``truncated``.
    assert result.get("truncated") is True
    assert result.get("nextFrom") == 15


def test_build_with_default_lines() -> None:
    """When ``lines`` is missing, ``default_lines`` is used."""
    content = "\n".join(str(i) for i in range(200))
    result = build_memory_read_result(content, "memory/note.md", default_lines=50)
    assert result.get("from") == 1
    assert result.get("lines") == 50


def test_build_max_chars_caps_text() -> None:
    """``maxChars`` caps the joined text length."""
    content = "x" * 100_000
    result = build_memory_read_result(content, "memory/note.md", max_chars=100)
    # The fitted text portion (before the notice) should be <= 100 chars.
    notice_idx = (result.get("text") or "").find("\n\n")
    if notice_idx >= 0:
        fitted = (result.get("text") or "")[:notice_idx]
    else:
        fitted = result.get("text") or ""
    assert len(fitted) <= 100


def test_build_suggest_read_fallback_propagates() -> None:
    """``suggest_read_fallback`` is forwarded to the slice helper."""
    content = "x" * 10_000
    result = build_memory_read_result(
        content, "memory/note.md", max_chars=5, suggest_read_fallback=True
    )
    assert "read on the source file" in (result.get("text") or "")


def test_build_content_shorter_than_requested() -> None:
    """When the file is shorter than the requested slice, the result
    contains only the available lines."""
    content = "a\nb"
    result = build_memory_read_result(content, "memory/note.md", from_=1, lines=100)
    assert result.get("lines") == 2
    assert result.get("truncated") is None
    assert result.get("nextFrom") is None


def test_build_default_lines_normalized() -> None:
    """OpenClaw's ``normalizePositiveInteger(0, fallback)`` returns 1
    (max(1, floor(0)) = 1), not the fallback. Only ``None`` /
    non-numeric values fall back to ``DEFAULT_MEMORY_READ_LINES``."""
    content = "\n".join(str(i) for i in range(300))
    result_zero = build_memory_read_result(content, "memory/note.md", default_lines=0)
    # 0 normalizes to 1.
    assert result_zero.get("lines") == 1

    result_none = build_memory_read_result(content, "memory/note.md", default_lines=None)
    # None falls back to DEFAULT_MEMORY_READ_LINES (120).
    assert result_none.get("lines") == 120


def test_build_from_normalized() -> None:
    """A from_ <= 0 is normalized to 1."""
    content = "\n".join(str(i) for i in range(10))
    result = build_memory_read_result(content, "memory/note.md", from_=-3, lines=2)
    assert result.get("from") == 1
    assert result.get("lines") == 2


def test_build_more_source_lines_remain_flag() -> None:
    """``more_source_lines_remain`` is computed from the slice vs total."""
    content = "\n".join(str(i) for i in range(20))
    result = build_memory_read_result(content, "memory/note.md", from_=1, lines=5)
    assert result.get("truncated") is True
    assert result.get("nextFrom") == 6


def test_build_continuation_notice_for_more() -> None:
    """When ``nextFrom`` is set, the notice carries the cursor."""
    content = "\n".join(str(i) for i in range(20))
    result = build_memory_read_result(content, "memory/note.md", from_=1, lines=3)
    assert f"from={result.get('nextFrom')}" in (result.get("text") or "")


def test_build_continuation_notice_for_budget_only() -> None:
    """When the budget was the only reason for truncation, the notice
    uses the budget-exceeded wording (no cursor)."""
    content = "x" * 50_000
    result = build_memory_read_result(content, "memory/note.md", max_chars=10)
    # Either no nextFrom (hard-truncated single line) or
    # nextFrom + cursor wording.
    if result.get("nextFrom") is not None:
        # nextFrom is set; cursor wording is used.
        assert f"from={result.get('nextFrom')}" in (result.get("text") or "")
    else:
        # hard-truncated; budget wording is used.
        assert "default maxChars budget" in (result.get("text") or "")
