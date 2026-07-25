"""Phase 5.8 gate: ``truncate.py`` against OpenClaw's own test vectors.

Every case in ``packages/agent-core/src/harness/utils/truncate.test.ts``
(63 lines) is ported here verbatim, plus the cases that file leaves
implicit but that a Python port can silently get wrong — chiefly the
UTF-16-vs-code-point divergence.

The surrogate cases are the reason this suite exists. In JavaScript
``"🤖🤖🤖".length`` is 6; in Python ``len(...)`` is 3. A transliterated
port passes every ASCII test and fails only on astral input, which in
practice means it fails on user filenames, CJK source files, and emoji in
commit messages — after shipping.
"""

from __future__ import annotations

import pytest

from jarvis_agent.truncate import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_LINES,
    GREP_MAX_LINE_LENGTH,
    code_unit_length,
    format_size,
    replace_unpaired_surrogates,
    truncate_head,
    truncate_line,
    truncate_tail,
    utf8_byte_length,
)

ROBOT = "\U0001f916"  # 🤖 U+1F916 — one astral char, two UTF-16 units
KANJI = "\U00020bb7"  # 𠮷 U+20BB7 — CJK Extension B, also two units
SMILE = "\U0001f642"  # 🙂 U+1F642 — 4 UTF-8 bytes

# Matches the JS regex in the "never produces unpaired surrogates" case:
# a high surrogate not followed by a low, or a low not preceded by a high.
_UNPAIRED_HIGH = range(0xD800, 0xDC00)
_UNPAIRED_LOW = range(0xDC00, 0xE000)


def _has_unpaired_surrogate(text: str) -> bool:
    for index, char in enumerate(text):
        point = ord(char)
        if point in _UNPAIRED_HIGH:
            following = ord(text[index + 1]) if index + 1 < len(text) else None
            if following is None or following not in _UNPAIRED_LOW:
                return True
        elif point in _UNPAIRED_LOW:
            preceding = ord(text[index - 1]) if index > 0 else None
            if preceding is None or preceding not in _UNPAIRED_HIGH:
                return True
    return False


# ── ported verbatim from truncate.test.ts ────────────────────────────


def test_does_not_count_trailing_newline_as_extra_display_line() -> None:
    """Vector: ``truncateHead("alpha\\nbeta\\n").totalLines === 2``."""
    assert truncate_head("alpha\nbeta\n").total_lines == 2
    assert truncate_tail("alpha\nbeta\n").total_lines == 2


def test_classifies_trailing_newline_truncation_by_the_byte_limit() -> None:
    """Vector: ``truncateHead("x\\n", { maxBytes: 1 }).truncatedBy === "bytes"``.

    Subtle: ``"x\\n"`` is *one* line by the counting rule above, so the
    line ceiling is not exceeded and the classification must come out as
    bytes. A port that counted two lines would report ``"lines"`` here.
    """
    assert truncate_head("x\n", max_bytes=1).truncated_by == "bytes"
    assert truncate_tail("x\n", max_bytes=1).truncated_by == "bytes"


def test_keeps_complete_utf8_characters_when_taking_a_partial_tail_line() -> None:
    """Vector: ``truncateTail("alpha🙂", { maxBytes: 4 })`` -> ``"🙂"``."""
    result = truncate_tail("alpha" + SMILE, max_bytes=4)

    assert result.content == SMILE
    assert result.last_line_partial is True
    assert result.output_bytes == 4


def test_truncate_line_returns_text_unchanged_when_within_limit() -> None:
    """Vector: ``truncateLine("short", 10)`` -> not truncated."""
    result = truncate_line("short", 10)
    assert result.text == "short"
    assert result.was_truncated is False


def test_truncate_line_truncates_and_appends_suffix_when_over_limit() -> None:
    """Vector: ``truncateLine("this is a very long line", 10)``."""
    result = truncate_line("this is a very long line", 10)
    assert result.was_truncated is True
    assert result.text == "this is a ... [truncated]"


def test_truncate_line_uses_grep_max_line_length_as_default() -> None:
    """Vector: ``truncateLine("x")`` uses ``GREP_MAX_LINE_LENGTH``."""
    result = truncate_line("x")
    assert result.was_truncated is False
    assert result.text == "x"


@pytest.mark.parametrize(
    ("line", "max_chars", "expected"),
    [
        # "AB" + 🤖 + "CD": cut at 3 would split the emoji, so back off to 2.
        ("AB" + ROBOT + "CD", 3, "AB... [truncated]"),
        # Three emoji (6 code units); cut at 5 lands mid-second-emoji.
        (ROBOT * 3, 5, ROBOT * 2 + "... [truncated]"),
        # CJK Extension B at the boundary stays intact; cut at 5 is safe.
        ("AB" + KANJI + "CD", 5, "AB" + KANJI + "C... [truncated]"),
    ],
)
def test_truncate_line_does_not_split_a_surrogate_pair(
    line: str, max_chars: int, expected: str
) -> None:
    """The three surrogate vectors from ``truncate.test.ts``.

    A naive Python port produces ``"AB🤖... [truncated]"``, ``"🤖🤖🤖"``
    (unchanged — it thinks the line is only 3 chars), and ``"AB𠮷CD"`` for
    these three respectively. All three are wrong.
    """
    assert truncate_line(line, max_chars).text == expected


@pytest.mark.parametrize(
    ("line", "max_chars"),
    [("AB" + ROBOT + "CD", 3), (ROBOT * 3, 5), ("AB" + KANJI + "CD", 5)],
)
def test_truncate_line_never_produces_unpaired_surrogates(line: str, max_chars: int) -> None:
    """Vector: the JS regex assertion, expressed as an explicit scan."""
    assert not _has_unpaired_surrogate(truncate_line(line, max_chars).text)


# ── cases the TS suite leaves implicit ───────────────────────────────


def test_code_unit_length_matches_javascript_string_length() -> None:
    """Guards the premise the whole module rests on.

    If this assertion is ever weakened, every surrogate vector above
    becomes meaningless, so it is stated as its own test rather than
    trusted as a comment.
    """
    assert code_unit_length("AB" + ROBOT + "CD") == 6
    assert len("AB" + ROBOT + "CD") == 5  # Python disagrees — that is the point
    assert code_unit_length(ROBOT * 3) == 6
    assert code_unit_length("AB" + KANJI + "CD") == 6
    assert code_unit_length("ascii") == 5
    assert code_unit_length("") == 0


def test_no_truncation_leaves_content_identical() -> None:
    """The most common path: content under both ceilings is returned as-is."""
    content = "alpha\nbeta\ngamma"
    result = truncate_head(content)
    assert result.content == content
    assert result.truncated is False
    assert result.truncated_by is None
    assert result.output_lines == 3
    assert result.total_lines == 3
    assert result.max_lines == DEFAULT_MAX_LINES
    assert result.max_bytes == DEFAULT_MAX_BYTES


def test_head_truncation_by_lines_keeps_the_first_lines() -> None:
    result = truncate_head("a\nb\nc\nd\ne", max_lines=2)
    assert result.content == "a\nb"
    assert result.truncated is True
    assert result.truncated_by == "lines"
    assert result.output_lines == 2
    assert result.total_lines == 5


def test_tail_truncation_by_lines_keeps_the_last_lines() -> None:
    """Tail must preserve *order*, not just membership.

    ``unshift`` in the TS builds the list front-to-back while walking
    backwards; a port that appended instead would return ``"e\\nd"``.
    """
    result = truncate_tail("a\nb\nc\nd\ne", max_lines=2)
    assert result.content == "d\ne"
    assert result.truncated is True
    assert result.truncated_by == "lines"
    assert result.output_lines == 2


def test_head_first_line_exceeding_byte_limit_yields_empty_output() -> None:
    """Head refuses to emit a partial line; tail is the one that may."""
    result = truncate_head("averylongfirstline\nsecond", max_bytes=5)
    assert result.content == ""
    assert result.output_lines == 0
    assert result.output_bytes == 0
    assert result.first_line_exceeds_limit is True
    assert result.truncated_by == "bytes"


def test_tail_partial_line_is_flagged_and_head_never_is() -> None:
    tail = truncate_tail("averylongsingleline", max_bytes=5)
    assert tail.last_line_partial is True
    assert tail.content == "eline"

    head = truncate_head("averylongsingleline", max_bytes=5)
    assert head.last_line_partial is False
    assert head.first_line_exceeds_limit is True


def test_empty_content_is_zero_lines_not_one() -> None:
    """``splitLinesForCounting("")`` returns ``[]``, not ``[""]``."""
    result = truncate_head("")
    assert result.total_lines == 0
    assert result.total_bytes == 0
    assert result.truncated is False
    assert result.content == ""


def test_explicit_zero_limit_is_honoured_not_defaulted() -> None:
    """``??`` keys off undefined, so an explicit 0 must survive.

    A port using ``max_bytes or DEFAULT_MAX_BYTES`` would silently turn a
    caller's ``0`` into 50KB and truncate nothing.
    """
    result = truncate_head("abc", max_bytes=0)
    assert result.max_bytes == 0
    assert result.truncated is True
    assert result.content == ""

    by_lines = truncate_head("a\nb", max_lines=0)
    assert by_lines.max_lines == 0
    assert by_lines.truncated is True


def test_multibyte_content_counts_bytes_not_characters() -> None:
    """``"🙂"`` is one character, two code units, and four bytes."""
    assert utf8_byte_length(SMILE) == 4
    assert utf8_byte_length("a" + SMILE) == 5
    assert truncate_head(SMILE).total_bytes == 4


def test_tail_byte_boundary_takes_whole_characters_only() -> None:
    """3 bytes is not enough for a 4-byte character, so nothing is kept."""
    result = truncate_tail("alpha" + SMILE, max_bytes=3)
    assert result.content == ""
    assert result.last_line_partial is True


def test_replace_unpaired_surrogates_repairs_lone_units_and_keeps_pairs() -> None:
    assert replace_unpaired_surrogates("ok") == "ok"
    assert replace_unpaired_surrogates(ROBOT) == ROBOT
    assert replace_unpaired_surrogates("a\ud83e") == "a�"
    assert replace_unpaired_surrogates("\udd16b") == "�b"


@pytest.mark.parametrize(
    ("num_bytes", "expected"),
    [
        (0, "0B"),
        (512, "512B"),
        (1023, "1023B"),
        (1024, "1.0KB"),
        (1536, "1.5KB"),
        (1024 * 1024 - 1, "1024.0KB"),
        (1024 * 1024, "1.0MB"),
        (3 * 1024 * 1024, "3.0MB"),
    ],
)
def test_format_size_boundaries(num_bytes: int, expected: str) -> None:
    """Parity: ``formatSize``. The 1023/1024 and 1MB-1/1MB edges matter."""
    assert format_size(num_bytes) == expected


def test_grep_max_line_length_constant_matches_openclaw() -> None:
    """Constants are part of the wire contract, not implementation detail."""
    assert GREP_MAX_LINE_LENGTH == 500
    assert DEFAULT_MAX_LINES == 2000
    assert DEFAULT_MAX_BYTES == 50 * 1024


def test_truncation_result_is_immutable() -> None:
    """Frozen dataclass: a caller cannot rewrite a truncation verdict."""
    result = truncate_head("a")
    with pytest.raises(Exception):  # FrozenInstanceError
        result.content = "tampered"  # type: ignore[misc]
