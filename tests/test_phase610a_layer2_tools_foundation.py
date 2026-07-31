"""Phase 6.10a — tools/ foundational types + helpers tests.

Verifies the foundational tool surface:
- tool_contracts — TypedDict shapes + the
  format_full_output_footer helper
- limits — byte-bounded tail helpers
  (SESSION_TOOL_STDERR_TAIL_BYTES,
  normalize_positive_limit,
  append_bounded_text_tail)
- truncate — re-exports from
  jarvis_agent.truncate (DEFAULT_MAX_LINES,
  DEFAULT_MAX_BYTES, GREP_MAX_LINE_LENGTH,
  truncate_head, truncate_tail, truncate_line,
  format_size)
- path_utils — resolve_to_cwd + resolve_read_path
  (with macOS variants)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.agents.sessions.tools import (
    BashToolDetails,
    BashToolInput,
    EditToolDetails,
    EditToolInput,
    FindToolDetails,
    FindToolInput,
    GrepToolDetails,
    GrepToolInput,
    LsToolDetails,
    LsToolInput,
    ReadToolDetails,
    ReadToolInput,
    ReadToolTruncationDetails,
    TruncationResult,
    WriteToolInput,
    format_full_output_footer,
    SESSION_TOOL_STDERR_TAIL_BYTES,
    append_bounded_text_tail,
    normalize_positive_limit,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_LINES,
    GREP_MAX_LINE_LENGTH,
    format_size,
    truncate_head,
    truncate_tail,
    truncate_line,
    resolve_read_path,
    resolve_to_cwd,
)


# ============================================================================
# tool_contracts
# ============================================================================


class TestToolContracts:
    def test_format_full_output_footer(self) -> None:
        assert format_full_output_footer("/tmp/out") == "Full output: /tmp/out"

    def test_inputs_total_false(self) -> None:
        # All Input TypedDicts are total=False
        # (every field is optional except where
        # the OpenClaw source marks required
        # — required fields are still typed).
        for cls in (
            BashToolInput,
            EditToolInput,
            FindToolInput,
            GrepToolInput,
            LsToolInput,
            ReadToolInput,
            WriteToolInput,
        ):
            assert getattr(cls, "__total__", None) is False

    def test_details_total_false(self) -> None:
        for cls in (
            BashToolDetails,
            FindToolDetails,
            GrepToolDetails,
            LsToolDetails,
        ):
            assert getattr(cls, "__total__", None) is False

    def test_truncation_result_reexport(self) -> None:
        # The TypedDict alias is preserved (any
        # non-None object). The Python port
        # uses ``jarvis_agent.truncate.TruncationResult``
        # at runtime; the TypedDict import is
        # a type-only alias.
        assert TruncationResult is not None

    def test_bash_input_shape(self) -> None:
        inp: BashToolInput = {"command": "ls", "timeout": 5000}
        assert inp["command"] == "ls"
        assert inp["timeout"] == 5000

    def test_read_input_shape(self) -> None:
        inp: ReadToolInput = {"path": "/foo", "offset": 10, "limit": 50}
        assert inp["path"] == "/foo"
        assert inp["offset"] == 10


# ============================================================================
# limits
# ============================================================================


class TestLimits:
    def test_default_stderr_tail_bytes(self) -> None:
        assert SESSION_TOOL_STDERR_TAIL_BYTES == 64 * 1024

    def test_normalize_positive_limit_with_value(self) -> None:
        assert normalize_positive_limit(100, 64) == 100

    def test_normalize_positive_limit_with_none(self) -> None:
        assert normalize_positive_limit(None, 64) == 64

    def test_normalize_positive_limit_with_zero(self) -> None:
        # The min=1 floor pushes 0 to 1.
        assert normalize_positive_limit(0, 64) == 1

    def test_normalize_positive_limit_with_negative(self) -> None:
        assert normalize_positive_limit(-10, 64) == 1

    def test_normalize_positive_limit_with_float(self) -> None:
        # 100.9 → floor → 100
        assert normalize_positive_limit(100.9, 64) == 100

    def test_append_bounded_text_tail_small_chunk(self) -> None:
        # Both under the limit
        result = append_bounded_text_tail("hello ", "world", max_bytes=100)
        assert result == "hello world"

    def test_append_bounded_text_tail_overflow(self) -> None:
        # current is long; chunk should be appended,
        # head of current should be dropped.
        result = append_bounded_text_tail(
            "a" * 50, "b" * 50, max_bytes=60
        )
        # Total bytes ≤ 60; the result is a tail
        # that contains the chunk + the tail of
        # the original.
        assert len(result.encode("utf-8")) <= 60
        assert "b" in result

    def test_append_bounded_text_tail_chunk_too_big(self) -> None:
        # chunk is bigger than max_bytes — only
        # the last ``max_bytes`` of the chunk
        # are kept.
        result = append_bounded_text_tail(
            "", "x" * 100, max_bytes=10
        )
        assert len(result.encode("utf-8")) <= 10

    def test_append_bounded_text_tail_unicode_safe(self) -> None:
        # Multi-byte characters should not be split.
        # Use 3-byte characters (Japanese).
        chunk = "日本語テスト"
        result = append_bounded_text_tail(
            "", chunk, max_bytes=100
        )
        assert result == chunk

    def test_append_bounded_text_tail_bytes_input(self) -> None:
        # bytes input is decoded as UTF-8.
        result = append_bounded_text_tail(
            "", "hello".encode("utf-8"), max_bytes=100
        )
        assert result == "hello"


# ============================================================================
# truncate
# ============================================================================


class TestTruncate:
    def test_defaults(self) -> None:
        assert DEFAULT_MAX_LINES == 2000
        assert DEFAULT_MAX_BYTES == 50 * 1024
        assert GREP_MAX_LINE_LENGTH == 500

    def test_truncate_head(self) -> None:
        text = "\n".join(str(i) for i in range(100))
        result = truncate_head(text, max_lines=10, max_bytes=100000)
        assert result.truncated is True
        # The Python port uses snake_case attrs
        # (``output_lines`` not ``outputLines``).
        assert result.output_lines == 10
        assert "0" in result.content
        assert "9" in result.content

    def test_truncate_tail(self) -> None:
        text = "\n".join(str(i) for i in range(100))
        result = truncate_tail(text, max_lines=10, max_bytes=100000)
        assert result.truncated is True
        assert "99" in result.content
        assert "90" in result.content

    def test_truncate_line(self) -> None:
        # ``truncate_line`` keeps the prefix of
        # a single long line; the Python port
        # uses ``max_chars`` not ``max_bytes``
        # + returns a ``TruncatedLine`` (with
        # ``was_truncated`` + ``text``). The
        # truncated text appends a marker so
        # the total length can exceed ``max_chars``
        # — we just confirm truncation happened
        # + the prefix is preserved.
        text = "a" * 1000
        result = truncate_line(text, max_chars=100)
        assert result.was_truncated is True
        # The text starts with the original prefix.
        assert result.text.startswith("a" * 100)

    def test_format_size(self) -> None:
        assert format_size(0) == "0B"
        assert format_size(1024) == "1.0KB"
        assert format_size(1024 * 1024) == "1.0MB"


# ============================================================================
# path_utils
# ============================================================================


class TestPathUtils:
    def test_resolve_to_cwd_absolute(self) -> None:
        # Absolute path is returned as-is
        # (after realpath normalisation).
        result = resolve_to_cwd("/etc/hosts", "/")
        assert os.path.isabs(result)
        # Should resolve to the real path
        assert result == os.path.realpath("/etc/hosts")

    def test_resolve_to_cwd_relative(self, tmp_path: Path) -> None:
        # Relative path is resolved against cwd
        os.chdir(tmp_path)
        subdir = tmp_path / "sub"
        subdir.mkdir()
        result = resolve_to_cwd("sub", str(tmp_path))
        assert result == str(subdir)

    def test_resolve_to_cwd_tilde(self) -> None:
        # Tilde expansion
        home = os.path.expanduser("~")
        result = resolve_to_cwd("~", "/")
        assert result == home

    def test_resolve_to_cwd_tilde_subpath(self) -> None:
        result = resolve_to_cwd("~/foo", "/")
        assert result == os.path.expanduser("~/foo")

    def test_resolve_to_cwd_at_prefix(self) -> None:
        # @-prefix is stripped; absolute paths
        # pass through realpath normalisation
        # (Windows joins with the drive root).
        result = resolve_to_cwd("@/foo", "/")
        assert result == os.path.realpath("/foo")

    def test_resolve_to_cwd_unicode_spaces(self) -> None:
        # Unicode spaces are normalised to ASCII
        result = resolve_to_cwd("/foo\u00a0bar", "/")
        assert "\u00a0" not in result

    def test_resolve_read_path_exists(
        self, tmp_path: Path
    ) -> None:
        # The canonical read path returns the
        # real path when the file exists.
        target = tmp_path / "file.txt"
        target.write_text("hello")
        result = resolve_read_path(str(target), str(tmp_path))
        assert os.path.isfile(result)
        assert result == str(target)

    def test_resolve_read_path_missing(self) -> None:
        # When the file doesn't exist, the
        # returned path is the resolved path
        # (the variants don't apply).
        result = resolve_read_path("/nonexistent/path", "/")
        assert result == os.path.realpath("/nonexistent/path")

    def test_resolve_read_path_am_pm_variant(
        self, tmp_path: Path
    ) -> None:
        # The OpenClaw source's AM/PM transform
        # (``path-utils.ts``) replaces the ASCII
        # space before ``AM`` / ``PM`` (not the
        # one between the hour and minutes) with
        # the narrow no-break space. We create
        # the file at the post-transform location
        # (narrow no-break space right before
        # ``PM``) and request the ASCII form.
        real = tmp_path / f"Screen Shot 2026-01-01 at 12 00.00{_NNBS}PM.png"
        real.write_text("png")
        ascii_form = "Screen Shot 2026-01-01 at 12 00.00 PM.png"
        result = resolve_read_path(ascii_form, str(tmp_path))
        assert result == str(real)

    def test_resolve_read_path_curly_quote_variant(
        self, tmp_path: Path
    ) -> None:
        # The curly-quote variant: file with
        # U+2019, request with U+0027.
        real = tmp_path / "Capture d\u2019\u00e9cran.png"
        real.write_text("png")
        straight = "Capture d'\u00e9cran.png"
        result = resolve_read_path(straight, str(tmp_path))
        assert result == str(real)


# Helper: narrow no-break space
_NNBS = "\u202f"
