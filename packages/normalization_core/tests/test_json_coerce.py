"""Parity tests for non-throwing JSON parsing."""

from __future__ import annotations

from jarvis_normalization_core.json_coerce import safe_parse_json, safe_parse_json_record


def test_safe_parse_json_values() -> None:
    assert safe_parse_json('{"a": 1}') == {"a": 1}
    assert safe_parse_json("[1, 2]") == [1, 2]
    assert safe_parse_json("42") == 42
    assert safe_parse_json("{bad}") is None
    assert safe_parse_json("") is None
    assert safe_parse_json(None) is None
    # JSON.parse rejects these; json.loads accepts them without parse_constant.
    assert safe_parse_json("NaN") is None
    assert safe_parse_json("Infinity") is None


def test_safe_parse_json_record_shapes() -> None:
    assert safe_parse_json_record('  {"a": 1}') == {"a": 1}
    assert safe_parse_json_record("[1]") is None
    assert safe_parse_json_record('"s"') is None
    assert safe_parse_json_record("42") is None
    assert safe_parse_json_record("{bad}") is None
    assert safe_parse_json_record(None) is None
