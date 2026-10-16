"""Parity tests for block parsing and user-text stripping.

Mirrors ``packages/tool-call-repair/src/payload.test.ts`` behaviors:
JSON + XML-ish block parsing, allowlists, payload caps, Harmony and
closing markers, and full-line stripping with protected ranges.

Named-bracket blocks require a closing marker (``[/name]`` or
``[END_TOOL_REQUEST]``); ``[tool:name]`` and Harmony blocks do not.
"""

from __future__ import annotations

import pytest
from jarvis_tool_call_repair import (
    DEFAULT_MAX_PLAIN_TEXT_TOOL_PAYLOAD_BYTES,
    JsonComplete,
    JsonInvalid,
    PlainTextToolCallParseOptions,
    PlainTextToolCallProtectedRange,
    parse_standalone_plain_text_tool_call_blocks,
    scan_plain_text_json_tool_call,
    scan_plain_text_tool_call,
    strip_plain_text_tool_call_blocks,
)


def test_bracket_json_block_with_closer() -> None:
    raw = '[read]\n{"path": "/tmp"}[/read]visible'
    scan = scan_plain_text_json_tool_call(raw)
    assert isinstance(scan, JsonComplete)
    assert raw[scan.end :] == "visible"
    blocks = parse_standalone_plain_text_tool_call_blocks('[read]\n{"path": "/tmp"}[/read]')
    assert blocks is not None
    assert [(block.name, block.arguments) for block in blocks] == [("read", {"path": "/tmp"})]
    assert blocks[0].start == 0


def test_tool_bracket_needs_no_closer() -> None:
    blocks = parse_standalone_plain_text_tool_call_blocks('[tool:read]{"path": "x"}')
    assert blocks is not None
    assert blocks[0].name == "read"


def test_named_bracket_requires_line_break() -> None:
    assert parse_standalone_plain_text_tool_call_blocks('[read]{"a": 1}') is None


def test_bare_json_at_eof_is_a_prefix_not_a_block() -> None:
    assert parse_standalone_plain_text_tool_call_blocks('[read]\n{"a": 1}') is None


def test_harmony_block_with_closings() -> None:
    text = '<|channel|>commentary to=read code<|message|>{"a": 1} <|call|>'
    blocks = parse_standalone_plain_text_tool_call_blocks(text)
    assert blocks is not None
    assert blocks[0].name == "read"
    assert blocks[0].arguments == {"a": 1}


def test_harmony_without_channel_marker() -> None:
    blocks = parse_standalone_plain_text_tool_call_blocks('analysis to=read code {"a": 1}')
    assert blocks is not None
    assert blocks[0].name == "read"


def test_end_tool_request_closes_named_bracket() -> None:
    raw = '[read]\n{"a": 1}[END_TOOL_REQUEST]'
    blocks = parse_standalone_plain_text_tool_call_blocks(raw)
    assert blocks is not None
    assert blocks[0].end == len(raw)


def test_wrong_named_closer_is_invalid() -> None:
    raw = '[read]\n{"path":"/tmp/file"}[/write] visible'
    scan = scan_plain_text_json_tool_call(raw)
    assert scan.kind == "invalid"
    assert isinstance(scan, JsonInvalid)
    assert raw[scan.at :] == "[/write] visible"


def test_120_char_names_accepted_121st_rejected() -> None:
    assert scan_plain_text_json_tool_call(f"[{'x' * 120}]\n{{}}[/{'x' * 120}]").kind == "complete"
    assert scan_plain_text_json_tool_call(f"[{'x' * 121}]\n{{}}").kind == "invalid"


def test_xmlish_block_parameters() -> None:
    blocks = parse_standalone_plain_text_tool_call_blocks(
        "<function=read><parameter=path>/tmp</parameter></function>"
    )
    assert blocks is not None
    assert blocks[0].arguments == {"path": "/tmp"}


def test_allowlist_filters_names() -> None:
    text = '[read]\n{"a": 1}[/read]'
    assert (
        parse_standalone_plain_text_tool_call_blocks(
            text, PlainTextToolCallParseOptions(allowed_tool_names=["write"])
        )
        is None
    )
    assert (
        parse_standalone_plain_text_tool_call_blocks(
            text, PlainTextToolCallParseOptions(allowed_tool_names=["read"])
        )
        is not None
    )


def test_payload_cap_rejects() -> None:
    text = '[read]\n{"a": "' + "x" * 300_000 + '"}[/read]'
    assert parse_standalone_plain_text_tool_call_blocks(text) is None
    assert (
        parse_standalone_plain_text_tool_call_blocks(
            text, PlainTextToolCallParseOptions(max_payload_bytes=10**9)
        )
        is not None
    )


def test_default_payload_cap_is_200k() -> None:
    assert DEFAULT_MAX_PLAIN_TEXT_TOOL_PAYLOAD_BYTES == 200_000


def test_malformed_json_rejects() -> None:
    assert parse_standalone_plain_text_tool_call_blocks("[read]\n{nope}[/read]") is None
    assert parse_standalone_plain_text_tool_call_blocks('[read]\n["a"][/read]') is None


def test_mixed_text_rejects_whole_parse() -> None:
    assert parse_standalone_plain_text_tool_call_blocks('hello\n[read]\n{"a": 1}') is None


def test_scan_progress_is_monotonic() -> None:
    first = scan_plain_text_tool_call("zzz[read]\n", 0)
    assert first.kind == "invalid"
    assert first.next > 0


def test_strip_removes_full_line_blocks() -> None:
    text = 'Hello\n[read]\n{"path": "/tmp"}\n[/read]\nWorld'
    assert strip_plain_text_tool_call_blocks(text) == "Hello\nWorld"


def test_strip_leaves_inline_and_prose() -> None:
    text = "use [read] for files"
    assert strip_plain_text_tool_call_blocks(text) == text
    assert strip_plain_text_tool_call_blocks("plain prose") == "plain prose"


def test_strip_honors_protected_ranges() -> None:
    text = '[read]\n{"a": 1}\n[/read]\n'
    protected = [PlainTextToolCallProtectedRange(start=0, end=5)]
    assert strip_plain_text_tool_call_blocks(text, lambda _: protected) == text


def test_strip_adjacent_blocks_together() -> None:
    text = "[a]\n{}\n[/a]\n[b]\n{}\n[/b]\ntail"
    assert strip_plain_text_tool_call_blocks(text) == "tail"


def test_strip_preserves_block_with_invalid_json() -> None:
    text = "Hello\n[read]\n{nope}\n[/read]\nWorld"
    assert strip_plain_text_tool_call_blocks(text) == text


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ('[tool:read]{"a": 1}', "read"),
        ('[read]\n{"a": 1}[/read]', "read"),
        ("<function=read><parameter=p>v</parameter></function>", "read"),
    ],
)
def test_scan_complete_syntaxes(text: str, name: str) -> None:
    scan = scan_plain_text_tool_call(text, 0)
    assert scan.kind == "complete"
    blocks = parse_standalone_plain_text_tool_call_blocks(text)
    assert blocks is not None
    assert blocks[0].name == name
