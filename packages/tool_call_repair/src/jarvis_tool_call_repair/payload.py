"""Block parsing and user-text stripping for plain-text tool calls.

OpenClaw parity: ``packages/tool-call-repair/src/payload.ts``.
Two syntax families: JSON payloads (``[name]`` / ``[tool:name]`` /
Harmony ``to=name`` + ``{...}``) and XML-ish payloads
(``<function=name>`` + ``<parameter=>`` spans). Only fully-valid
blocks parse; prefixes/invalids carry monotonic scan progress for
the streaming consumer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from jarvis_normalization_core.json_coerce import safe_parse_json_record

from .contracts import (
    NormalizedParseOptions,
    PlainTextToolCallNameMatcher,
    PlainTextToolCallParseOptions,
    PlainTextToolCallProtectedRange,
    is_offset_in_protected_ranges,
    normalize_parse_options,
)
from .grammar import (
    END_TOOL_REQUEST,
    HARMONY_CALL_MARKER,
    HARMONY_CHANNEL_MARKER,
    HARMONY_MESSAGE_MARKER,
    Span,
    StructuralLineBreaks,
    XmlishComplete,
    XmlishInvalid,
    XmlishPrefix,
    consume_line_break,
    consume_structural_line_break_after_horizontal_whitespace,
    is_plain_text_tool_name_char,
    scan_xmlish_tool_call,
    skip_horizontal_whitespace,
    skip_line_indentation,
    skip_whitespace,
    utf8_byte_length_within_limit,
)

DEFAULT_MAX_PLAIN_TEXT_TOOL_PAYLOAD_BYTES = 200_000
MAX_PLAIN_TEXT_TOOL_NAME_CHARS = 120
_HARMONY_CHANNELS = ("commentary", "analysis", "final")

JsonSyntax = Literal["harmony", "named-bracket", "tool-bracket"]


@dataclass(frozen=True, slots=True)
class PlainTextToolCallBlock:
    """Parsed standalone block with source offsets for repair."""

    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    raw: str = ""
    start: int = 0
    end: int = 0


@dataclass(frozen=True, slots=True)
class JsonState:
    """Incremental JSON brace-tracker state."""

    depth: int = 0
    escaped: bool = False
    in_string: bool = False


@dataclass(frozen=True, slots=True)
class JsonCandidate:
    """A JSON-syntax candidate (complete or prefix)."""

    syntax: JsonSyntax = "named-bracket"
    name: Span = field(default_factory=Span)
    name_complete: bool = False
    payload: Span | None = None
    json: JsonState | None = None


@dataclass(frozen=True, slots=True)
class JsonInvalid:
    kind: Literal["invalid"] = "invalid"
    at: int = 0
    candidate: JsonCandidate | None = None


@dataclass(frozen=True, slots=True)
class JsonPrefix:
    kind: Literal["prefix"] = "prefix"
    candidate: JsonCandidate | None = None


@dataclass(frozen=True, slots=True)
class JsonComplete:
    kind: Literal["complete"] = "complete"
    syntax: JsonSyntax = "named-bracket"
    name: Span = field(default_factory=Span)
    name_complete: Literal[True] = True
    payload: Span = field(default_factory=Span)
    end: int = 0


JsonScan = JsonInvalid | JsonPrefix | JsonComplete


def _is_literal_prefix_at(text: str, start: int, literal: str) -> bool:
    available = len(text) - start
    return start >= 0 and available < len(literal) and literal.startswith(text[start:])


def _scan_tool_name_end(text: str, start: int) -> int | None:
    end = start
    while end < len(text) and is_plain_text_tool_name_char(text[end]):
        if end - start == MAX_PLAIN_TEXT_TOOL_NAME_CHARS:
            return None
        end += 1
    return end


def _candidate(
    syntax: JsonSyntax,
    name: Span,
    name_complete: bool,
    payload: Span | None = None,
    json: JsonState | None = None,
) -> JsonCandidate:
    return JsonCandidate(
        syntax=syntax, name=name, name_complete=name_complete, payload=payload, json=json
    )


@dataclass(frozen=True, slots=True)
class _Opening:
    kind: Literal["complete", "prefix", "invalid"]
    cursor: int | None = None
    at: int | None = None
    candidate: JsonCandidate | None = None


def _scan_bracket_opening(text: str, start: int, breaks: StructuralLineBreaks | None) -> _Opening:
    """Scan ``[name]`` / ``[tool:name]``."""
    cursor = start + 1
    syntax: JsonSyntax = "named-bracket"
    if text.startswith("tool:", cursor):
        syntax = "tool-bracket"
        cursor += len("tool:")
    elif _is_literal_prefix_at(text, cursor, "tool:"):
        return _Opening(kind="prefix")
    name_start = cursor
    name_end = _scan_tool_name_end(text, name_start)
    if name_end is None:
        return _Opening(kind="invalid", at=name_start + MAX_PLAIN_TEXT_TOOL_NAME_CHARS)
    name = Span(name_start, name_end)
    cursor = name_end
    if cursor == len(text):
        return _Opening(
            kind="prefix",
            candidate=None if name_start == name_end else _candidate(syntax, name, False),
        )
    if name_start == name_end or (cursor < len(text) and text[cursor] != "]"):
        return _Opening(kind="invalid", at=cursor)
    cursor += 1
    value = _candidate(syntax, name, True)
    if syntax == "named-bracket":
        horizontal_end = skip_horizontal_whitespace(text, cursor)
        if horizontal_end == len(text):
            return _Opening(kind="prefix", candidate=value)
        after_break = consume_structural_line_break_after_horizontal_whitespace(
            text, cursor, breaks
        )
        if after_break is None:
            return _Opening(kind="invalid", at=horizontal_end, candidate=value)
        cursor = after_break
    return _Opening(kind="complete", cursor=cursor, candidate=value)


def _scan_harmony_opening(text: str, start: int) -> _Opening:
    """Scan Harmony ``<|channel|>... to=name ...``."""
    cursor = start
    if text.startswith(HARMONY_CHANNEL_MARKER, cursor):
        cursor += len(HARMONY_CHANNEL_MARKER)
    elif _is_literal_prefix_at(text, cursor, HARMONY_CHANNEL_MARKER):
        return _Opening(kind="prefix")
    elif cursor < len(text) and text[cursor] == "<":
        return _Opening(kind="invalid", at=cursor)

    channel = next((value for value in _HARMONY_CHANNELS if text.startswith(value, cursor)), None)
    if channel is None:
        if any(_is_literal_prefix_at(text, cursor, value) for value in _HARMONY_CHANNELS):
            return _Opening(kind="prefix")
        return _Opening(kind="invalid", at=cursor)
    cursor += len(channel)
    if cursor == len(text):
        return _Opening(kind="prefix")
    if text[cursor] not in (" ", "\t"):
        return _Opening(kind="invalid", at=cursor)
    cursor = skip_horizontal_whitespace(text, cursor)
    if not text.startswith("to=", cursor):
        if _is_literal_prefix_at(text, cursor, "to="):
            return _Opening(kind="prefix")
        return _Opening(kind="invalid", at=cursor)
    cursor += len("to=")

    name_start = cursor
    name_end = _scan_tool_name_end(text, name_start)
    if name_end is None:
        return _Opening(kind="invalid", at=name_start + MAX_PLAIN_TEXT_TOOL_NAME_CHARS)
    name = Span(name_start, name_end)
    cursor = name_end
    if cursor == len(text):
        return _Opening(
            kind="prefix",
            candidate=None if name_start == name_end else _candidate("harmony", name, False),
        )
    if name_start == name_end or (cursor < len(text) and text[cursor] not in (" ", "\t")):
        return _Opening(kind="invalid", at=cursor)
    cursor = skip_horizontal_whitespace(text, cursor)
    value = _candidate("harmony", name, True)
    if not text.startswith("code", cursor):
        if _is_literal_prefix_at(text, cursor, "code"):
            return _Opening(kind="prefix", candidate=value)
        return _Opening(kind="invalid", at=cursor, candidate=value)
    cursor = skip_whitespace(text, cursor + len("code"))
    if text.startswith(HARMONY_MESSAGE_MARKER, cursor):
        cursor = skip_whitespace(text, cursor + len(HARMONY_MESSAGE_MARKER))
    elif _is_literal_prefix_at(text, cursor, HARMONY_MESSAGE_MARKER):
        return _Opening(kind="prefix", candidate=value)
    elif cursor < len(text) and text[cursor] == "<":
        return _Opening(kind="invalid", at=cursor, candidate=value)
    return _Opening(kind="complete", cursor=cursor, candidate=value)


def _scan_json_object(text: str, start: int) -> tuple[str, int, JsonState]:
    """Scan one balanced ``{...}``; ``prefix`` when the text ends first."""
    depth = 0
    escaped = False
    in_string = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return ("complete", index + 1, JsonState(depth, escaped, in_string))
    return ("prefix", len(text), JsonState(depth, escaped, in_string))


def scan_plain_text_json_tool_call(
    text: str, start: int = 0, breaks: StructuralLineBreaks | None = None
) -> JsonScan:
    """Uncapped structural scan shared by parsing, stripping, and buffering."""
    opening = (
        _scan_bracket_opening(text, start, breaks)
        if start < len(text) and text[start] == "["
        else _scan_harmony_opening(text, start)
    )
    if opening.kind != "complete":
        if opening.kind == "prefix":
            return JsonPrefix(candidate=opening.candidate)
        return JsonInvalid(
            at=opening.at if opening.at is not None else start,
            candidate=opening.candidate,
        )

    cursor = opening.cursor
    value = opening.candidate
    assert cursor is not None and value is not None
    payload_start = skip_whitespace(text, cursor)
    if payload_start == len(text):
        return JsonPrefix(candidate=value)
    if text[payload_start] != "{":
        return JsonInvalid(at=payload_start, candidate=value)

    json_kind, json_end, state = _scan_json_object(text, payload_start)
    payload = Span(payload_start, json_end)
    if json_kind == "prefix":
        return JsonPrefix(candidate=_candidate(value.syntax, value.name, True, payload, state))

    closing_candidate = _candidate(value.syntax, value.name, True, payload, state)
    if value.syntax != "named-bracket":
        marker_start = skip_whitespace(text, json_end)
        name = text[value.name.start : value.name.end]
        closings = [HARMONY_CALL_MARKER, END_TOOL_REQUEST, f"[/{name}]"]
        for closing in closings:
            if text.startswith(closing, marker_start):
                return JsonComplete(
                    syntax=value.syntax,
                    name=value.name,
                    payload=payload,
                    end=marker_start + len(closing),
                )
            if marker_start < len(text) and _is_literal_prefix_at(text, marker_start, closing):
                return JsonPrefix(candidate=closing_candidate)
        return JsonComplete(syntax=value.syntax, name=value.name, payload=payload, end=json_end)

    closing_start = skip_whitespace(text, json_end)
    if closing_start == len(text):
        return JsonPrefix(candidate=closing_candidate)
    name = text[value.name.start : value.name.end]
    closings = [END_TOOL_REQUEST, f"[/{name}]"]
    for closing in closings:
        if text.startswith(closing, closing_start):
            return JsonComplete(
                syntax=value.syntax,
                name=value.name,
                payload=payload,
                end=closing_start + len(closing),
            )
        if _is_literal_prefix_at(text, closing_start, closing):
            return JsonPrefix(candidate=closing_candidate)
    return JsonInvalid(at=closing_start, candidate=closing_candidate)


@dataclass(frozen=True, slots=True)
class ToolCallScan:
    """One classified JSON/XML candidate with monotonic scan progress."""

    kind: Literal["complete", "prefix", "invalid"] = "invalid"
    end: int = 0
    next: int = 0
    over_cap: bool = False
    payload_start: int | None = None
    complete_end: int | None = None
    at: int | None = None


def scan_plain_text_tool_call(
    text: str,
    start: int = 0,
    matcher: PlainTextToolCallNameMatcher | None = None,
    max_payload_bytes: int | None = None,
    breaks: StructuralLineBreaks | None = None,
) -> ToolCallScan:
    """Classify one JSON/XML candidate and provide monotonic scan progress."""
    xmlish = scan_xmlish_tool_call(text, start, breaks)
    json = scan_plain_text_json_tool_call(text, start, breaks)
    cap = (
        max_payload_bytes
        if max_payload_bytes is not None
        else DEFAULT_MAX_PLAIN_TEXT_TOOL_PAYLOAD_BYTES
    )

    def allowed(name: str | None, name_complete: bool, is_prefix: bool) -> bool:
        if name is None:
            return is_prefix
        if matcher is None:
            return True
        if name_complete:
            return matcher.has_exact_name(name)
        return matcher.has_name_prefix(name)

    def xmlish_parts() -> tuple[str | None, bool, Span | None, bool]:
        if isinstance(xmlish, XmlishComplete):
            return (
                text[xmlish.name.start : xmlish.name.end],
                True,
                xmlish.payload,
                False,
            )
        candidate = xmlish.candidate
        if candidate is None:
            return (None, False, None, isinstance(xmlish, XmlishPrefix))
        return (
            text[candidate.name.start : candidate.name.end],
            candidate.name_complete,
            candidate.payload,
            False,
        )

    def json_parts() -> tuple[str | None, bool, Span | None, bool]:
        if isinstance(json, JsonComplete):
            return (
                text[json.name.start : json.name.end],
                True,
                json.payload,
                False,
            )
        if json.candidate is None:
            return (None, False, None, isinstance(json, JsonPrefix))
        candidate = json.candidate
        return (
            text[candidate.name.start : candidate.name.end],
            candidate.name_complete,
            candidate.payload,
            False,
        )

    xml_name, xml_complete, xml_payload, xml_bare_prefix = xmlish_parts()
    json_name, json_complete, json_payload, json_bare_prefix = json_parts()
    xml_accepted = allowed(xml_name, xml_complete, xml_bare_prefix)
    json_accepted = allowed(json_name, json_complete, json_bare_prefix)

    def over_cap(payload: Span | None) -> bool:
        return bool(
            payload is not None
            and utf8_byte_length_within_limit(text, payload.start, payload.end, cap) is None
        )

    xml_over_cap = over_cap(xml_payload)
    json_over_cap = over_cap(json_payload)

    if xml_accepted and isinstance(xmlish, XmlishComplete):
        return ToolCallScan(
            kind="complete",
            end=xmlish.end,
            next=xmlish.end,
            over_cap=xml_over_cap,
            payload_start=xmlish.payload.start,
        )
    if json_accepted and isinstance(json, JsonComplete):
        payload_args = _parse_json_arguments(text, json.payload)
        if json_over_cap or payload_args is not None:
            return ToolCallScan(
                kind="complete",
                end=json.end,
                next=json.end,
                over_cap=json_over_cap,
                payload_start=json.payload.start,
            )
        return ToolCallScan(
            kind="invalid",
            at=json.end,
            next=json.end,
            payload_start=json.payload.start,
        )
    if xml_accepted and isinstance(xmlish, XmlishInvalid) and xml_over_cap and xml_payload:
        return ToolCallScan(
            kind="invalid",
            at=xmlish.at,
            next=xmlish.at,
            over_cap=True,
            payload_start=xml_payload.start,
        )
    if (
        json_accepted
        and isinstance(json, JsonInvalid)
        and json_over_cap
        and json_payload is not None
    ):
        return ToolCallScan(
            kind="invalid",
            at=json.at,
            next=json.at,
            over_cap=True,
            payload_start=json_payload.start,
        )

    xml_prefix = xml_accepted and isinstance(xmlish, XmlishPrefix)
    json_prefix = json_accepted and isinstance(json, JsonPrefix)
    if xml_prefix or json_prefix:
        payload = xml_payload if xml_prefix else json_payload
        complete_end = (
            xmlish.complete_end
            if isinstance(xmlish, XmlishPrefix) and xmlish.complete_end is not None
            else None
        )
        return ToolCallScan(
            kind="prefix",
            next=len(text),
            over_cap=over_cap(payload),
            payload_start=payload.start if payload is not None else None,
            complete_end=complete_end,
        )

    advance = start + 1
    if xml_accepted:
        advance = max(advance, xmlish.at if isinstance(xmlish, XmlishInvalid) else len(text))
    if json_accepted:
        if isinstance(json, JsonComplete):
            advance = max(advance, json.end)
        elif isinstance(json, JsonInvalid):
            advance = max(advance, json.at)
        else:
            advance = max(advance, len(text))
    return ToolCallScan(kind="invalid", at=advance, next=advance)


def _parse_json_arguments(text: str, payload: Span) -> dict[str, Any] | None:
    return safe_parse_json_record(text[payload.start : payload.end])


def _parse_block_at(
    text: str,
    start: int,
    options: NormalizedParseOptions | None,
    breaks: StructuralLineBreaks | None,
) -> PlainTextToolCallBlock | None:
    scan = scan_plain_text_json_tool_call(text, start, breaks)
    if not isinstance(scan, JsonComplete):
        return None
    name = text[scan.name.start : scan.name.end]
    if options is not None and options.allowed_tool_names is not None:
        if name not in options.allowed_tool_names:
            return None
    cap = (
        options.max_payload_bytes
        if options is not None and options.max_payload_bytes is not None
        else DEFAULT_MAX_PLAIN_TEXT_TOOL_PAYLOAD_BYTES
    )
    if utf8_byte_length_within_limit(text, scan.payload.start, scan.payload.end, cap) is None:
        return None
    arguments = _parse_json_arguments(text, scan.payload)
    if arguments is None:
        return None
    return PlainTextToolCallBlock(
        name=name, arguments=arguments, raw=text[start : scan.end], start=start, end=scan.end
    )


def _extract_xmlish_parameter_value(
    text: str, start: int, end: int, breaks: StructuralLineBreaks | None
) -> str:
    value = text[start:end]
    if consume_line_break(text, skip_horizontal_whitespace(text, start)) is None:
        boundary = consume_structural_line_break_after_horizontal_whitespace(text, start, breaks)
        if boundary is not None:
            offset = boundary - start
            value = f"{value[:offset]}\n{value[offset:]}"
    payload_start = consume_line_break(value, 0)
    if payload_start is None:
        return value
    return re.sub(r"(?:\r\n|[\r\n])$", "", value[payload_start:])


def _parse_xmlish_block_at(
    text: str,
    start: int,
    options: NormalizedParseOptions | None,
    breaks: StructuralLineBreaks | None,
) -> PlainTextToolCallBlock | None:
    scan = scan_xmlish_tool_call(text, start, breaks)
    if not isinstance(scan, XmlishComplete):
        return None
    name = text[scan.name.start : scan.name.end]
    if options is not None and options.allowed_tool_names is not None:
        if name not in options.allowed_tool_names:
            return None
    cap = (
        options.max_payload_bytes
        if options is not None and options.max_payload_bytes is not None
        else DEFAULT_MAX_PLAIN_TEXT_TOOL_PAYLOAD_BYTES
    )
    if utf8_byte_length_within_limit(text, scan.payload.start, scan.payload.end, cap) is None:
        return None
    args = {
        text[parameter.name.start : parameter.name.end]: _extract_xmlish_parameter_value(
            text, parameter.value.start, parameter.value.end, breaks
        )
        for parameter in scan.parameters
    }
    return PlainTextToolCallBlock(
        name=name, arguments=args, raw=text[start : scan.end], start=start, end=scan.end
    )


def parse_standalone_plain_text_tool_call_blocks(
    text: str,
    options: PlainTextToolCallParseOptions | None = None,
    breaks: StructuralLineBreaks | None = None,
) -> list[PlainTextToolCallBlock] | None:
    """Parse standalone blocks covering the whole text (whitespace-separated)."""
    normalized = normalize_parse_options(options)
    blocks: list[PlainTextToolCallBlock] = []
    cursor = skip_whitespace(text, 0)
    while cursor < len(text):
        block = _parse_block_at(text, cursor, normalized, breaks) or _parse_xmlish_block_at(
            text, cursor, normalized, breaks
        )
        if block is None:
            return None
        blocks.append(block)
        cursor = skip_whitespace(text, block.end)
    return blocks or None


_STRIP_FAST_PATHS = (
    re.compile(r"\[(?:tool:)?[A-Za-z0-9_-]+\]"),
    re.compile(r"(?:^|[\r\n])[^\S\r\n]*(?:<\|channel\|>)?(?:commentary|analysis|final)[ \t]+to="),
    re.compile(r"(?:^|[\r\n])[^\S\r\n]*<function=", re.IGNORECASE),
)


def strip_plain_text_tool_call_blocks(
    text: str,
    resolve_protected_ranges: Any = None,
) -> str:
    """Remove full-line standalone tool-call blocks from user-visible text."""
    if not text or not (
        _STRIP_FAST_PATHS[0].search(text)
        or _STRIP_FAST_PATHS[1].search(text)
        or _STRIP_FAST_PATHS[2].search(text)
    ):
        return text
    protected: list[PlainTextToolCallProtectedRange] = (
        resolve_protected_ranges(text) if resolve_protected_ranges else []
    )
    result = ""
    cursor = 0
    index = 0
    while index < len(text):
        line_start = index == 0 or text[index - 1] in ("\n", "\r")
        if not line_start:
            index += 1
            continue
        block_start = skip_line_indentation(text, index)
        if is_offset_in_protected_ranges(block_start, protected):
            index += 1
            continue
        scan = scan_plain_text_tool_call(text, block_start)
        if scan.kind == "prefix" and scan.complete_end is None:
            return result + text[cursor:]
        if scan.kind == "invalid":
            # The scanner owns everything before `next` as one malformed
            # candidate; honor that progress so nested line starts inside
            # its payload are not rescanned quadratically.
            index = max(index + 1, scan.next)
            continue
        block_end = scan.end if scan.kind == "complete" else scan.complete_end
        if block_end is None:
            return result + text[cursor:]
        result += text[cursor:index]
        while True:
            adjacent_start = skip_line_indentation(text, block_end)
            if is_offset_in_protected_ranges(adjacent_start, protected):
                break
            adjacent = scan_plain_text_tool_call(text, adjacent_start)
            adjacent_end = (
                adjacent.end
                if adjacent.kind == "complete"
                else adjacent.complete_end
                if adjacent.kind == "prefix"
                else None
            )
            if adjacent_end is None or adjacent_end <= block_end:
                break
            block_end = adjacent_end
        line_break_start = skip_line_indentation(text, block_end)
        if line_break_start == len(text):
            cursor = line_break_start
        else:
            consumed = consume_line_break(text, line_break_start)
            cursor = consumed if consumed is not None else block_end
        index = cursor
    result += text[cursor:]
    return result


__all__ = [
    "DEFAULT_MAX_PLAIN_TEXT_TOOL_PAYLOAD_BYTES",
    "MAX_PLAIN_TEXT_TOOL_NAME_CHARS",
    "JsonCandidate",
    "JsonComplete",
    "JsonInvalid",
    "JsonPrefix",
    "JsonScan",
    "JsonState",
    "PlainTextToolCallBlock",
    "ToolCallScan",
    "parse_standalone_plain_text_tool_call_blocks",
    "scan_plain_text_json_tool_call",
    "scan_plain_text_tool_call",
    "strip_plain_text_tool_call_blocks",
]
