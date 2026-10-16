"""Parity tests for the structural scanner.

Mirrors ``packages/tool-call-repair/src/grammar.test.ts`` vectors.
"""

from __future__ import annotations

import pytest
from jarvis_tool_call_repair import (
    XmlishComplete,
    XmlishInvalid,
    XmlishPrefix,
    scan_xmlish_tool_call,
    utf8_byte_length_within_limit,
)
from jarvis_tool_call_repair.grammar import skip_line_indentation, skip_whitespace


def _complete(raw: str, start: int = 0) -> XmlishComplete:
    scan = scan_xmlish_tool_call(raw, start)
    assert isinstance(scan, XmlishComplete)
    return scan


def _prefix(raw: str, start: int = 0) -> XmlishPrefix:
    scan = scan_xmlish_tool_call(raw, start)
    assert isinstance(scan, XmlishPrefix)
    return scan


@pytest.mark.parametrize(
    "raw",
    [
        "<function=read>",
        "<function=read></func",
        "<function=read><parameter=path>/tmp/file",
        "[tool:read]<parameter=path>/tmp/file",
        "[read]\n<parameter=path>/tmp/file",
    ],
)
def test_incomplete_syntax_stays_prefix(raw: str) -> None:
    assert scan_xmlish_tool_call(raw).kind == "prefix"


@pytest.mark.parametrize(
    "raw",
    [
        "<function=get_system_info></function>",
        "<function=read><parameter=path>/tmp/file</parameter></function>",
        "[tool:read]<parameter=path>/tmp/file</parameter>",
        "[read]\n<parameter=path>/tmp/file</parameter></function>",
    ],
)
def test_complete_forms(raw: str) -> None:
    assert _complete(f"{raw}\nvisible").end == len(raw)


def test_120_char_names_accepted_at_both_boundaries() -> None:
    name = "x" * 120
    scan = scan_xmlish_tool_call(f"<function={name}><parameter={name}>value</parameter></function>")
    assert scan.kind == "complete"


def test_name_case_preserved_tags_matched_insensitively() -> None:
    raw = "<FuNcTiOn=Read><PaRaMeTeR=Path>value</pArAmEtEr></fUnCtIoN>"
    scan = _complete(raw)
    assert raw[scan.name.start : scan.name.end] == "Read"
    parameter = scan.parameters[0]
    assert raw[parameter.name.start : parameter.name.end] == "Path"


@pytest.mark.parametrize(
    "raw",
    [
        "[tool:get_system_info]</function>",
        "[get_system_info]\n</function>",
        f"<function={'x' * 121}></function>",
        f"<function={'x' * 121}",
        "<function=read><parameter=" + "x" * 121 + ">value</parameter></function>",
        "<function=read><parameter=" + "x" * 121,
    ],
)
def test_invalid_or_ambiguous_forms_rejected(raw: str) -> None:
    assert scan_xmlish_tool_call(raw).kind == "invalid"


def test_absolute_spans() -> None:
    call = "\n".join(
        ["<function=write>", "<parameter=content>", "  hello", "</parameter>", "</function>"]
    )
    raw = f"  {call}\nvisible"
    scan = _complete(raw, 2)
    assert raw[scan.name.start : scan.name.end] == "write"
    assert raw[scan.payload.start : scan.payload.end] == (
        "\n<parameter=content>\n  hello\n</parameter>\n"
    )
    assert len(scan.parameters) == 1
    parameter = scan.parameters[0]
    assert raw[parameter.name.start : parameter.name.end] == "content"
    assert raw[parameter.value.start : parameter.value.end] == "\n  hello\n"
    assert scan.end == 2 + len(call)


def test_incomplete_body_span_for_limit_enforcement() -> None:
    raw = f"<function=read>{chr(0xA0) * 128_001}"
    scan = _prefix(raw)
    assert scan.candidate is not None and scan.candidate.payload is not None
    assert len(raw) < 256_000
    payload = scan.candidate.payload
    assert payload is not None
    assert utf8_byte_length_within_limit(raw, payload.start, payload.end, 256_000) is None


def test_partial_close_excluded_from_payload_cap() -> None:
    body = " " * 255_999
    prefix = f"<function=read>{body}</func"
    scan = _prefix(prefix)
    assert scan.candidate is not None and scan.candidate.payload is not None
    payload = scan.candidate.payload
    assert payload is not None
    assert utf8_byte_length_within_limit(prefix, payload.start, payload.end, 256_000) == 255_999
    assert scan_xmlish_tool_call(f"{prefix}tion>").kind == "complete"


@pytest.mark.parametrize("suffix", ["</func", "<param"])
def test_complete_close_retained_before_ambiguous_prefix(suffix: str) -> None:
    complete = "[tool:read]<parameter=path>/tmp/file</parameter>"
    scan = _prefix(f"{complete}{suffix}")
    assert scan.complete_end == len(complete)


def test_first_visible_byte_after_invalid_over_cap_prefix() -> None:
    visible = "Visible answer"
    raw = f"<function=read>{chr(0xA0) * 128_001}{visible}"
    scan = scan_xmlish_tool_call(raw)
    assert isinstance(scan, XmlishInvalid)
    assert raw[scan.at :] == visible


def test_whitespace_matches_javascript_character_classes() -> None:
    assert skip_line_indentation("\u00a0\u2003x", 0) == 2
    assert skip_line_indentation("\u0085x", 0) == 0
    assert skip_whitespace("\u00a0\ufeffx", 0) == 2
    assert skip_whitespace("\u001cx", 0) == 0
