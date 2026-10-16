"""Parity tests for provider-id normalization.

Mirrors the ``normalizeProviderId`` / ``findNormalizedProvider*``
contracts from ``packages/model-catalog-core/src/provider-id.ts``.
"""

from __future__ import annotations

from jarvis_model_catalog import (
    find_normalized_provider_key,
    find_normalized_provider_value,
    normalize_provider_id,
    normalize_provider_id_for_auth,
)


def test_normalize_provider_id_lowercases_and_trims() -> None:
    assert normalize_provider_id("  OpenAI ") == "openai"
    assert normalize_provider_id("ANTHROPIC") == "anthropic"


def test_normalize_provider_id_non_string_is_empty() -> None:
    assert normalize_provider_id(None) == ""
    assert normalize_provider_id(42) == ""


def test_normalize_provider_id_for_auth_matches() -> None:
    assert normalize_provider_id_for_auth(" Google ") == "google"


def test_find_normalized_provider_value_case_insensitive() -> None:
    entries = {"OpenAI": 1, "anthropic": 2}
    assert find_normalized_provider_value(entries, "openai") == 1
    assert find_normalized_provider_value(entries, "ANTHROPIC") == 2
    assert find_normalized_provider_value(entries, "missing") is None
    assert find_normalized_provider_value(None, "openai") is None
    assert find_normalized_provider_value({}, "openai") is None


def test_find_normalized_provider_key_returns_declared_key() -> None:
    entries = {"OpenAI": 1}
    assert find_normalized_provider_key(entries, "openai") == "OpenAI"
    assert find_normalized_provider_key(entries, "missing") is None
