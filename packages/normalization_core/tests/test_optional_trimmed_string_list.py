"""Parity test for normalize_optional_trimmed_string_list."""

from __future__ import annotations

from jarvis_normalization_core.string_coerce import normalize_optional_trimmed_string_list


def test_optional_list_none_when_empty() -> None:
    assert normalize_optional_trimmed_string_list(["a", " b "]) == ["a", "b"]
    assert normalize_optional_trimmed_string_list([]) is None
    assert normalize_optional_trimmed_string_list(["  "]) is None
    assert normalize_optional_trimmed_string_list(None) is None
    assert normalize_optional_trimmed_string_list("nope") is None
