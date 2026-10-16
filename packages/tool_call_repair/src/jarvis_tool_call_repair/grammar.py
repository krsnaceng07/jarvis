"""Structural scanner primitives for plain-text tool-call repair.

OpenClaw parity: ``packages/tool-call-repair/src/grammar.ts``.
Character-level, allocation-light scanning shared by parsing,
stripping, and (later) stream buffering. Offsets are UTF-16 code
units in TS; Python indexes Unicode code points, so offsets are
only comparable within one runtime — never persisted across
runtimes (parity note: the wire contract carries strings, not
offsets). Whitespace skipping uses ``str.isspace``, a superset of
the JS whitespace class (it also matches NEL U+0085); scanner
decisions agree on every input the grammar targets.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

#: Legacy marker some models emit after a serialized JSON tool request.
END_TOOL_REQUEST = "[END_TOOL_REQUEST]"
#: Harmony stream marker introducing the target channel before a tool call.
HARMONY_CHANNEL_MARKER = "<|channel|>"
#: Harmony stream marker that may separate the header from the JSON payload.
HARMONY_MESSAGE_MARKER = "<|message|>"
#: Harmony stream marker that may close a serialized tool-call payload.
HARMONY_CALL_MARKER = "<|call|>"

_PLAIN_TEXT_TOOL_NAME_RE = re.compile(r"[A-Za-z0-9_-]")
_XMLISH_NAME_RE = re.compile(r"[A-Za-z0-9_.:-]")
_LINE_WHITESPACE_RE = re.compile(
    r"[\t\v\f \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]"
)
_JS_WHITESPACE_RE = re.compile(
    r"[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]"
)


def is_plain_text_tool_name_char(char: str | None) -> bool:
    """Tool names in repairs match provider-safe ids only."""
    return bool(char and _PLAIN_TEXT_TOOL_NAME_RE.search(char))


def is_xmlish_name_char(char: str | None) -> bool:
    """XML-ish function tags allow namespace punctuation."""
    return bool(char and _XMLISH_NAME_RE.search(char))


def _char_at(text: str, index: int) -> str | None:
    return text[index] if 0 <= index < len(text) else None


def skip_horizontal_whitespace(text: str, start: int) -> int:
    """Skip spaces and tabs only, preserving line boundaries."""
    index = start
    while index < len(text) and text[index] in (" ", "\t"):
        index += 1
    return index


def skip_line_indentation(text: str, start: int) -> int:
    """Skip indentation whitespace without crossing the line boundary.

    Mirrors JS ``[^\\S\\r\\n]*`` behavior, including non-breaking spaces.
    """
    index = start
    while index < len(text) and _LINE_WHITESPACE_RE.fullmatch(text[index]):
        index += 1
    return index


def skip_whitespace(text: str, start: int) -> int:
    """Skip all whitespace when line structure is no longer meaningful.

    Mirrors JavaScript ``/\\s/`` rather than Python's wider ``isspace()``.
    """
    index = start
    while index < len(text) and _JS_WHITESPACE_RE.fullmatch(text[index]):
        index += 1
    return index


def consume_line_break(text: str, start: int) -> int | None:
    """Consume Unix or Windows line endings; ``None`` when absent."""
    char = _char_at(text, start)
    if char == "\r":
        return start + 2 if _char_at(text, start + 1) == "\n" else start + 1
    if char == "\n":
        return start + 1
    return None


@dataclass(frozen=True, slots=True)
class StructuralLineBreaks:
    """Structural line-break offsets plus the used-offset sink."""

    line_break_offsets: frozenset[int] = frozenset()
    used_line_break_offsets: set[int] | None = None


def consume_structural_line_break_after_horizontal_whitespace(
    text: str, start: int, breaks: StructuralLineBreaks | None = None
) -> int | None:
    """Consume a line break after horizontal whitespace, or a structural one."""
    right = skip_horizontal_whitespace(text, start)
    actual = consume_line_break(text, right)
    if actual is not None:
        return actual
    if breaks is not None:
        for offset in range(start, right + 1):
            if offset in breaks.line_break_offsets:
                if breaks.used_line_break_offsets is not None:
                    breaks.used_line_break_offsets.add(offset)
                return offset
    return None


def utf8_byte_length_within_limit(text: str, start: int, end: int, max_bytes: int) -> int | None:
    """Encoded byte length of a span, or ``None`` when over the limit."""
    if end - start > max_bytes:
        return None
    byte_length = len(text[start:end].encode("utf-8"))
    return byte_length if byte_length <= max_bytes else None


@dataclass(frozen=True, slots=True)
class Span:
    """Inclusive-start/exclusive-end source span."""

    start: int = 0
    end: int = 0


@dataclass(frozen=True, slots=True)
class XmlishParameterSpan:
    """Name/value spans of one XML-ish parameter."""

    name: Span = field(default_factory=Span)
    value: Span = field(default_factory=Span)


XmlishSyntax = Literal["function", "named-bracket", "tool-bracket"]


@dataclass(frozen=True, slots=True)
class XmlishCandidate:
    """A parsed XML-ish candidate (complete or prefix)."""

    syntax: XmlishSyntax = "function"
    name: Span = field(default_factory=Span)
    name_complete: bool = False
    parameters: tuple[XmlishParameterSpan, ...] = ()
    payload: Span | None = None
    active_parameter_open_end: int | None = None


@dataclass(frozen=True, slots=True)
class XmlishInvalid:
    """No call opens here; ``at`` is the failure offset."""

    kind: Literal["invalid"] = "invalid"
    at: int = 0
    candidate: XmlishCandidate | None = None


@dataclass(frozen=True, slots=True)
class XmlishPrefix:
    """A call prefix; ``complete_end`` is static-strip-safe only."""

    kind: Literal["prefix"] = "prefix"
    candidate: XmlishCandidate | None = None
    complete_end: int | None = None


@dataclass(frozen=True, slots=True)
class XmlishComplete:
    """A complete call with its end offset."""

    kind: Literal["complete"] = "complete"
    syntax: XmlishSyntax = "function"
    name: Span = field(default_factory=Span)
    name_complete: bool = True
    parameters: tuple[XmlishParameterSpan, ...] = ()
    payload: Span = field(default_factory=Span)
    end: int = 0


XmlishScan = XmlishInvalid | XmlishPrefix | XmlishComplete

_FUNCTION_OPEN = "<function="
_FUNCTION_CLOSE = "</function>"
_PARAMETER_OPEN = "<parameter="
_PARAMETER_CLOSE = "</parameter>"


def starts_with_ascii_marker_ignore_case(text: str, cursor: int, marker: str) -> bool:
    """Case-insensitive marker match at ``cursor``."""
    return text[cursor : cursor + len(marker)].lower() == marker


def is_ascii_marker_prefix_ignore_case(text: str, cursor: int, marker: str) -> bool:
    """True when the text at ``cursor`` is a strict prefix of ``marker``."""
    rest = text[cursor : cursor + len(marker)].lower()
    return len(rest) < len(marker) and marker.startswith(rest)


def index_of_ascii_marker_ignore_case(text: str, marker: str, start: int) -> int:
    """Case-insensitive ``indexOf`` for ``<``-led markers from ``start``."""
    cursor = text.find("<", start)
    while cursor != -1:
        if starts_with_ascii_marker_ignore_case(text, cursor, marker):
            return cursor
        cursor = text.find("<", cursor + 1)
    return -1


def _scan_name(text: str, start: int, char_test: Callable[[str | None], bool]) -> int:
    cursor = start
    while cursor < len(text) and char_test(text[cursor]) and cursor - start < 121:
        cursor += 1
    return cursor


def scan_xmlish_tool_call(
    text: str, start: int = 0, breaks: StructuralLineBreaks | None = None
) -> XmlishScan:
    """Uncapped structural scan shared by parsing, stripping, and buffering."""
    cursor = start
    char = _char_at(text, cursor)

    if char == "<":
        if not (
            starts_with_ascii_marker_ignore_case(text, cursor, _FUNCTION_OPEN)
            or is_ascii_marker_prefix_ignore_case(text, cursor, _FUNCTION_OPEN)
        ):
            return XmlishInvalid(at=start)
        if len(text) - cursor < len(_FUNCTION_OPEN):
            return XmlishPrefix()
        cursor += len(_FUNCTION_OPEN)
        name_start = cursor
        cursor = _scan_name(text, cursor, is_xmlish_name_char)
        name = Span(name_start, cursor)
        syntax: XmlishSyntax = "function"
        if cursor - name_start > 120:
            return XmlishInvalid(at=cursor)
        if cursor == len(text):
            return XmlishPrefix(
                candidate=XmlishCandidate(syntax=syntax, name=name, name_complete=False)
            )
        if cursor == name_start or _char_at(text, cursor) != ">":
            return XmlishInvalid(at=cursor)
        cursor += 1
    elif char == "[":
        cursor += 1
        first_start = cursor
        cursor = _scan_name(text, cursor, is_plain_text_tool_name_char)
        if cursor - first_start > 120:
            return XmlishInvalid(at=cursor)
        first_name = text[first_start:cursor]
        if cursor == len(text) and "tool".startswith(first_name):
            return XmlishPrefix()
        syntax = "named-bracket"
        name = Span(first_start, cursor)
        if _char_at(text, cursor) == ":" and first_name == "tool":
            syntax = "tool-bracket"
            cursor += 1
            name_start = cursor
            cursor = _scan_name(text, cursor, is_plain_text_tool_name_char)
            name = Span(name_start, cursor)
            if cursor - name_start > 120:
                return XmlishInvalid(at=cursor)
        if cursor == len(text):
            return XmlishPrefix(
                candidate=XmlishCandidate(syntax=syntax, name=name, name_complete=False)
            )
        if name.start == name.end or _char_at(text, cursor) != "]":
            return XmlishInvalid(at=cursor)
        cursor += 1
        if syntax == "named-bracket":
            if cursor == len(text):
                return XmlishPrefix(
                    candidate=XmlishCandidate(syntax=syntax, name=name, name_complete=True)
                )
            after_break = consume_structural_line_break_after_horizontal_whitespace(
                text, cursor, breaks
            )
            if after_break is None:
                return XmlishInvalid(at=cursor)
            cursor = after_break
    else:
        return XmlishInvalid(at=start)

    body_start = cursor
    parameters: list[XmlishParameterSpan] = []

    def _candidate(payload_end: int, active_open_end: int | None = None) -> XmlishCandidate:
        return XmlishCandidate(
            syntax=syntax,
            name=name,
            name_complete=True,
            parameters=tuple(parameters),
            payload=Span(body_start, payload_end),
            active_parameter_open_end=active_open_end,
        )

    def _prefix(payload_end: int, active_open_end: int | None = None) -> XmlishPrefix:
        return XmlishPrefix(
            candidate=_candidate(payload_end, active_open_end),
            complete_end=last_parameter_end if syntax == "tool-bracket" else None,
        )

    def _complete(payload_end: int, end: int | None = None) -> XmlishComplete:
        return XmlishComplete(
            syntax=syntax,
            name=name,
            parameters=tuple(parameters),
            payload=Span(body_start, payload_end),
            end=payload_end if end is None else end,
        )

    last_parameter_end: int | None = None
    while True:
        marker_start = skip_whitespace(text, cursor)
        if marker_start == len(text):
            if syntax == "tool-bracket" and last_parameter_end is not None:
                return _complete(last_parameter_end)
            return XmlishPrefix(candidate=_candidate(len(text)))
        if starts_with_ascii_marker_ignore_case(text, marker_start, _FUNCTION_CLOSE):
            if syntax != "function" and not parameters:
                return XmlishInvalid(at=marker_start, candidate=_candidate(marker_start))
            return _complete(marker_start, marker_start + len(_FUNCTION_CLOSE))
        if is_ascii_marker_prefix_ignore_case(text, marker_start, _FUNCTION_CLOSE):
            return _prefix(marker_start)
        if starts_with_ascii_marker_ignore_case(text, marker_start, _PARAMETER_OPEN):
            param_name_start = marker_start + len(_PARAMETER_OPEN)
            param_name_end = _scan_name(text, param_name_start, is_xmlish_name_char)
            if param_name_end - param_name_start > 120:
                return XmlishInvalid(at=marker_start, candidate=_candidate(marker_start))
            if param_name_end == len(text):
                return _prefix(marker_start)
            if param_name_end == param_name_start or _char_at(text, param_name_end) != ">":
                return XmlishInvalid(at=marker_start, candidate=_candidate(marker_start))
            value_start = param_name_end + 1
            close_start = index_of_ascii_marker_ignore_case(text, _PARAMETER_CLOSE, value_start)
            if close_start == -1:
                return _prefix(len(text), value_start)
            end = close_start + len(_PARAMETER_CLOSE)
            parameters.append(
                XmlishParameterSpan(
                    name=Span(param_name_start, param_name_end),
                    value=Span(value_start, close_start),
                )
            )
            cursor = end
            last_parameter_end = end
            continue
        if is_ascii_marker_prefix_ignore_case(text, marker_start, _PARAMETER_OPEN):
            return _prefix(marker_start)
        if syntax == "tool-bracket" and last_parameter_end is not None:
            return _complete(last_parameter_end)
        return XmlishInvalid(at=marker_start, candidate=_candidate(marker_start))


__all__ = [
    "END_TOOL_REQUEST",
    "HARMONY_CALL_MARKER",
    "HARMONY_CHANNEL_MARKER",
    "HARMONY_MESSAGE_MARKER",
    "StructuralLineBreaks",
    "Span",
    "XmlishCandidate",
    "XmlishComplete",
    "XmlishInvalid",
    "XmlishParameterSpan",
    "XmlishPrefix",
    "XmlishScan",
    "XmlishSyntax",
    "consume_line_break",
    "consume_structural_line_break_after_horizontal_whitespace",
    "index_of_ascii_marker_ignore_case",
    "is_ascii_marker_prefix_ignore_case",
    "is_plain_text_tool_name_char",
    "is_xmlish_name_char",
    "scan_xmlish_tool_call",
    "skip_horizontal_whitespace",
    "skip_line_indentation",
    "skip_whitespace",
    "starts_with_ascii_marker_ignore_case",
    "utf8_byte_length_within_limit",
]
