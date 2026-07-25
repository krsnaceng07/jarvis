"""jarvis_agent.truncate — line/byte truncation for tool output.

OpenClaw parity: ``packages/agent-core/src/harness/utils/truncate.ts``.

Why this module needs unusual care
==================================
Tool output truncation looks like string slicing, but it is the boundary
where a model's view of a file, a grep hit, or a command's stdout is
decided. Two properties matter:

1. **Byte ceilings are enforced in UTF-8 bytes**, because that is what a
   provider bills and what a transport limits — not characters.
2. **Character ceilings are enforced in UTF-16 code units**, because that
   is what JavaScript's ``String.prototype.length`` counts, and this is a
   port that must produce byte-identical output to OpenClaw.

Point 2 is the trap. In JavaScript ``"🤖🤖🤖".length`` is ``6``; in Python
``len("🤖🤖🤖")`` is ``3``. A direct transliteration using ``len()`` and
``str`` slicing silently shifts every cut point, and all three surrogate
test vectors in ``truncate.test.ts`` fail. So this module carries an
explicit code-unit layer (:func:`_to_code_units` / :func:`_from_code_units`)
and :func:`truncate_line` operates on it.

``surrogatepass`` is used for that conversion so a lone surrogate — which
is exactly what a naive cut through an astral character produces — is
representable rather than an encoding error. It is then repaired by
:func:`replace_unpaired_surrogates`, matching the TypeScript.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Literal

#: Parity: ``DEFAULT_MAX_LINES`` in ``truncate.ts``.
DEFAULT_MAX_LINES = 2000

#: Parity: ``DEFAULT_MAX_BYTES`` — 50KB.
DEFAULT_MAX_BYTES = 50 * 1024

#: Parity: ``GREP_MAX_LINE_LENGTH`` — max chars per grep match line.
GREP_MAX_LINE_LENGTH = 500

#: The suffix appended by :func:`truncate_line`. Kept as a constant because
#: callers match on it when re-rendering tool output.
TRUNCATED_LINE_SUFFIX = "... [truncated]"

#: U+FFFD, substituted for any surrogate left unpaired by a cut.
REPLACEMENT_CHARACTER = "�"

TruncatedBy = Literal["lines", "bytes"]


@dataclass(frozen=True, slots=True)
class TruncationResult:
    """Result metadata for content truncated by line count, byte count, or both.

    Parity: the ``TruncationResult`` interface in ``truncate.ts``. Field
    docs are carried over so callers do not have to consult the TS.
    """

    #: The truncated content.
    content: str
    #: Whether truncation occurred.
    truncated: bool
    #: Which limit was hit: ``"lines"``, ``"bytes"``, or ``None``.
    truncated_by: TruncatedBy | None
    #: Total number of lines in the original content.
    total_lines: int
    #: Total number of bytes in the original content.
    total_bytes: int
    #: Number of complete lines in the truncated output.
    output_lines: int
    #: Number of bytes in the truncated output.
    output_bytes: int
    #: Whether the last line was partially truncated (tail edge case only).
    last_line_partial: bool = False
    #: Whether the first line exceeded the byte limit (head truncation).
    first_line_exceeds_limit: bool = False
    #: The max lines limit that was applied.
    max_lines: int = DEFAULT_MAX_LINES
    #: The max bytes limit that was applied.
    max_bytes: int = DEFAULT_MAX_BYTES


@dataclass(frozen=True, slots=True)
class TruncatedLine:
    """Return shape of :func:`truncate_line`.

    Parity: ``{ text, wasTruncated }`` in ``truncate.ts``.
    """

    text: str
    was_truncated: bool


@dataclass(frozen=True, slots=True)
class _ResolvedTruncationInput:
    """Parity: the internal ``ResolvedTruncationInput`` interface."""

    lines: list[str]
    total_lines: int
    total_bytes: int
    max_lines: int
    max_bytes: int


# ── UTF-16 code-unit layer ───────────────────────────────────────────
#
# This has no counterpart in the TypeScript because JS strings *are*
# sequences of UTF-16 code units. In Python the view must be built.


def _to_code_units(text: str) -> list[int]:
    """Return *text* as the list of UTF-16 code units JavaScript would see.

    ``surrogatepass`` keeps lone surrogates representable, so this is
    lossless for any ``str`` — including one already holding an unpaired
    surrogate from an earlier cut.
    """
    data = text.encode("utf-16-le", "surrogatepass")
    return list(struct.unpack(f"<{len(data) // 2}H", data))


def _from_code_units(units: list[int]) -> str:
    """Inverse of :func:`_to_code_units`. May yield lone surrogates."""
    if not units:
        return ""
    data = struct.pack(f"<{len(units)}H", *units)
    return data.decode("utf-16-le", "surrogatepass")


def code_unit_length(text: str) -> int:
    """Length of *text* in UTF-16 code units — JavaScript's ``.length``.

    Exposed because callers that compare against ``GREP_MAX_LINE_LENGTH``
    must measure the same way this module cuts, or they will disagree
    with it about whether a line needs truncating.
    """
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def _is_high_surrogate(unit: int) -> bool:
    return 0xD800 <= unit <= 0xDBFF


def _is_low_surrogate(unit: int) -> bool:
    return 0xDC00 <= unit <= 0xDFFF


# ── byte counting ────────────────────────────────────────────────────


def _split_lines_for_counting(content: str) -> list[str]:
    """Parity: ``splitLinesForCounting``.

    A single trailing newline is a line *terminator*, not an extra empty
    line — so ``"alpha\\nbeta\\n"`` is two lines, and the test vector
    ``totalLines == 2`` depends on this ``pop()``.
    """
    if len(content) == 0:
        return []
    lines = content.split("\n")
    if content.endswith("\n"):
        lines.pop()
    return lines


def utf8_byte_length(content: str) -> int:
    """UTF-8 byte length of *content*. Parity: ``utf8ByteLength``.

    The TypeScript prefers ``Buffer.byteLength`` and falls back to a manual
    code-unit walk. Python's ``str.encode`` is the direct equivalent of the
    former, so the fallback branch is not ported — but the *surrogate*
    handling is: an unpaired surrogate counts as 3 bytes (the length of the
    U+FFFD it will be replaced by), which is what the TS fallback computes
    and what ``"strict"`` encoding would instead refuse to do.
    """
    try:
        return len(content.encode("utf-8"))
    except UnicodeEncodeError:
        # Contains unpaired surrogates. Count them the way the TS does.
        total = 0
        for unit in _to_code_units(content):
            if _is_high_surrogate(unit) or _is_low_surrogate(unit):
                total += 3
            elif unit <= 0x7F:
                total += 1
            elif unit <= 0x7FF:
                total += 2
            else:
                total += 3
        # Paired surrogates were counted as 3+3=6 above but encode to 4.
        units = _to_code_units(content)
        for index in range(len(units) - 1):
            if _is_high_surrogate(units[index]) and _is_low_surrogate(units[index + 1]):
                total -= 2
        return total


def replace_unpaired_surrogates(content: str) -> str:
    """Parity: ``replaceUnpairedSurrogates``.

    Paired surrogates are preserved as their astral character; an unpaired
    one on either side becomes U+FFFD. Without this a cut through an emoji
    would emit an invalid string that no provider can encode.
    """
    units = _to_code_units(content)
    out: list[int] = []
    index = 0
    while index < len(units):
        unit = units[index]
        if _is_high_surrogate(unit):
            if index + 1 < len(units) and _is_low_surrogate(units[index + 1]):
                out.append(unit)
                out.append(units[index + 1])
                index += 2
                continue
            out.extend(_to_code_units(REPLACEMENT_CHARACTER))
        elif _is_low_surrogate(unit):
            out.extend(_to_code_units(REPLACEMENT_CHARACTER))
        else:
            out.append(unit)
        index += 1
    return _from_code_units(out)


def format_size(num_bytes: int) -> str:
    """Format byte counts for compact tool-output diagnostics.

    Parity: ``formatSize``. ``toFixed(1)`` maps to ``f"{value:.1f}"``;
    both round half away from zero at one decimal for these magnitudes.
    """
    if num_bytes < 1024:
        return f"{num_bytes}B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f}KB"
    return f"{num_bytes / (1024 * 1024):.1f}MB"


def _resolve_truncation_input(
    content: str,
    max_lines: int | None,
    max_bytes: int | None,
) -> _ResolvedTruncationInput:
    """Parity: ``resolveTruncationInput``.

    ``None`` means "not supplied" and takes the default, matching TS
    ``options.maxLines ?? DEFAULT_MAX_LINES``. Note ``??`` keys off
    ``undefined``/``null`` only, so an explicit ``0`` is honoured — which
    is why this checks ``is None`` rather than falsiness.
    """
    resolved_lines = DEFAULT_MAX_LINES if max_lines is None else max_lines
    resolved_bytes = DEFAULT_MAX_BYTES if max_bytes is None else max_bytes
    total_bytes = utf8_byte_length(content)
    lines = _split_lines_for_counting(content)
    return _ResolvedTruncationInput(
        lines=lines,
        total_lines=len(lines),
        total_bytes=total_bytes,
        max_lines=resolved_lines,
        max_bytes=resolved_bytes,
    )


def _build_truncation_result(
    input_: _ResolvedTruncationInput,
    *,
    content: str,
    truncated: bool,
    truncated_by: TruncatedBy | None,
    output_lines: int,
    output_bytes: int | None = None,
    last_line_partial: bool = False,
    first_line_exceeds_limit: bool = False,
) -> TruncationResult:
    """Parity: ``buildTruncationResult``."""
    return TruncationResult(
        content=content,
        truncated=truncated,
        truncated_by=truncated_by,
        total_lines=input_.total_lines,
        total_bytes=input_.total_bytes,
        output_lines=output_lines,
        output_bytes=utf8_byte_length(content) if output_bytes is None else output_bytes,
        last_line_partial=last_line_partial,
        first_line_exceeds_limit=first_line_exceeds_limit,
        max_lines=input_.max_lines,
        max_bytes=input_.max_bytes,
    )


def truncate_head(
    content: str,
    *,
    max_lines: int | None = None,
    max_bytes: int | None = None,
) -> TruncationResult:
    """Keep the beginning of content, respecting line and byte ceilings.

    Parity: ``truncateHead``. Head truncation preserves complete lines; a
    first line that exceeds the byte ceiling produces empty output and
    sets ``first_line_exceeds_limit`` — it does *not* emit a partial line,
    because a half-line of head output reads as if the file started that
    way. Tail truncation makes the opposite trade (see :func:`truncate_tail`).
    """
    input_ = _resolve_truncation_input(content, max_lines, max_bytes)

    if input_.total_lines <= input_.max_lines and input_.total_bytes <= input_.max_bytes:
        return _build_truncation_result(
            input_,
            content=content,
            truncated=False,
            truncated_by=None,
            output_lines=input_.total_lines,
            output_bytes=input_.total_bytes,
        )

    first_line = input_.lines[0] if input_.lines else None
    if first_line is not None and utf8_byte_length(first_line) > input_.max_bytes:
        return _build_truncation_result(
            input_,
            content="",
            truncated=True,
            truncated_by="bytes",
            output_lines=0,
            output_bytes=0,
            first_line_exceeds_limit=True,
        )

    output_lines_arr: list[str] = []
    output_bytes_count = 0
    truncated_by: TruncatedBy = "lines" if input_.total_lines > input_.max_lines else "bytes"

    for index, line in enumerate(input_.lines[: input_.max_lines]):
        line_bytes = utf8_byte_length(line) + (1 if index > 0 else 0)  # +1 for newline

        if output_bytes_count + line_bytes > input_.max_bytes:
            truncated_by = "bytes"
            break

        output_lines_arr.append(line)
        output_bytes_count += line_bytes

    if (
        input_.total_lines > input_.max_lines
        and len(output_lines_arr) >= input_.max_lines
        and output_bytes_count <= input_.max_bytes
    ):
        truncated_by = "lines"

    return _build_truncation_result(
        input_,
        content="\n".join(output_lines_arr),
        truncated=True,
        truncated_by=truncated_by,
        output_lines=len(output_lines_arr),
    )


def truncate_tail(
    content: str,
    *,
    max_lines: int | None = None,
    max_bytes: int | None = None,
) -> TruncationResult:
    """Keep the end of content, respecting line and byte ceilings.

    Parity: ``truncateTail``. Tail truncation preserves recent output for
    command errors, and unlike head truncation it *may* keep a partial
    first line: when one final line alone exceeds the ceiling, the end of
    that line is more useful than nothing, because the interesting part of
    an error is at its end.
    """
    input_ = _resolve_truncation_input(content, max_lines, max_bytes)

    if input_.total_lines <= input_.max_lines and input_.total_bytes <= input_.max_bytes:
        return _build_truncation_result(
            input_,
            content=content,
            truncated=False,
            truncated_by=None,
            output_lines=input_.total_lines,
            output_bytes=input_.total_bytes,
        )

    output_lines_arr: list[str] = []
    output_bytes_count = 0
    truncated_by: TruncatedBy = "lines" if input_.total_lines > input_.max_lines else "bytes"
    last_line_partial = False

    index = len(input_.lines) - 1
    while index >= 0 and len(output_lines_arr) < input_.max_lines:
        line = input_.lines[index]
        line_bytes = utf8_byte_length(line) + (1 if output_lines_arr else 0)  # +1 for newline

        if output_bytes_count + line_bytes > input_.max_bytes:
            truncated_by = "bytes"
            # Edge case: no lines added yet and this line exceeds max_bytes,
            # so take the end of the line (partial).
            if not output_lines_arr:
                truncated_line = _truncate_string_to_bytes_from_end(line, input_.max_bytes)
                output_lines_arr.insert(0, truncated_line)
                output_bytes_count = utf8_byte_length(truncated_line)
                last_line_partial = True
            break

        output_lines_arr.insert(0, line)
        output_bytes_count += line_bytes
        index -= 1

    if (
        input_.total_lines > input_.max_lines
        and len(output_lines_arr) >= input_.max_lines
        and output_bytes_count <= input_.max_bytes
    ):
        truncated_by = "lines"

    return _build_truncation_result(
        input_,
        content="\n".join(output_lines_arr),
        truncated=True,
        truncated_by=truncated_by,
        output_lines=len(output_lines_arr),
        last_line_partial=last_line_partial,
    )


def _truncate_string_to_bytes_from_end(text: str, max_bytes: int) -> str:
    """Truncate *text* to fit ``max_bytes``, keeping the end.

    Parity: ``truncateStringToBytesFromEnd``. Walks backwards a whole
    character at a time so a multi-byte sequence is never split: the
    ``truncateTail("alpha🙂", { maxBytes: 4 })`` vector returns exactly
    ``"🙂"`` (4 bytes) rather than a mangled 4-byte prefix of it.
    """
    if max_bytes <= 0:
        return ""

    units = _to_code_units(text)
    output_bytes = 0
    start = len(units)
    needs_replacement = False

    index = len(units)
    while index > 0:
        character_start = index - 1
        unit = units[character_start]
        unpaired_surrogate = False

        if _is_low_surrogate(unit) and character_start > 0:
            previous = units[character_start - 1]
            if _is_high_surrogate(previous):
                character_start -= 1
                character_bytes = 4
            else:
                character_bytes = 3
                unpaired_surrogate = True
        elif _is_high_surrogate(unit) or _is_low_surrogate(unit):
            character_bytes = 3
            unpaired_surrogate = True
        elif unit <= 0x7F:
            character_bytes = 1
        elif unit <= 0x7FF:
            character_bytes = 2
        else:
            character_bytes = 3

        if output_bytes + character_bytes > max_bytes:
            break

        output_bytes += character_bytes
        start = character_start
        needs_replacement = needs_replacement or unpaired_surrogate
        index = character_start

    output = _from_code_units(units[start:])
    return replace_unpaired_surrogates(output) if needs_replacement else output


def truncate_line(line: str, max_chars: int = GREP_MAX_LINE_LENGTH) -> TruncatedLine:
    """Trim a display line and mark it with the grep-style suffix.

    Parity: ``truncateLine``. ``max_chars`` counts **UTF-16 code units**,
    not Python characters — see the module docstring. The cut point is
    backed off by one unit when it would split a surrogate pair, so an
    emoji or CJK Extension B character crossing the boundary is dropped
    whole instead of rendering as a replacement character.
    """
    units = _to_code_units(line)
    if len(units) <= max_chars:
        return TruncatedLine(text=line, was_truncated=False)

    cut = max_chars
    # Avoid splitting a surrogate pair at the truncation boundary.
    if cut < len(units) and cut > 0:
        last_unit = units[cut - 1]
        if _is_high_surrogate(last_unit) and _is_low_surrogate(units[cut]):
            cut -= 1

    return TruncatedLine(
        text=_from_code_units(units[:cut]) + TRUNCATED_LINE_SUFFIX,
        was_truncated=True,
    )


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_LINES",
    "GREP_MAX_LINE_LENGTH",
    "REPLACEMENT_CHARACTER",
    "TRUNCATED_LINE_SUFFIX",
    "TruncatedBy",
    "TruncatedLine",
    "TruncationResult",
    "code_unit_length",
    "format_size",
    "replace_unpaired_surrogates",
    "truncate_head",
    "truncate_line",
    "truncate_tail",
    "utf8_byte_length",
]
