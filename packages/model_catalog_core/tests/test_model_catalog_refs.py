"""Parity tests for catalog refs and merge keys.

Mirrors ``packages/model-catalog-core/src/model-catalog-refs.ts``
plus the ``model-catalog-refs.test.ts`` vectors.
"""

from __future__ import annotations

from jarvis_model_catalog import (
    build_model_catalog_merge_key,
    build_model_catalog_ref,
    is_cloud_model_ref,
    parse_model_catalog_ref,
    parse_provider_model_ref,
)


def test_build_model_catalog_ref_normalizes_provider() -> None:
    assert build_model_catalog_ref("OpenAI", "gpt-5") == "openai/gpt-5"


def test_parse_provider_model_ref_strict() -> None:
    parsed = parse_provider_model_ref("openai/gpt-5")
    assert parsed is not None
    assert (parsed.provider, parsed.model) == ("openai", "gpt-5")
    # No interior slash, or an empty segment, is not a ref.
    assert parse_provider_model_ref("gpt-5") is None
    assert parse_provider_model_ref("/gpt-5") is None
    assert parse_provider_model_ref("openai/") is None
    assert parse_provider_model_ref("  openai / gpt-5  ") is not None


def test_parse_model_catalog_ref_normalizes_provider_only() -> None:
    parsed = parse_model_catalog_ref("OpenAI/gpt-5")
    assert parsed is not None
    assert parsed.provider == "openai"
    assert parsed.model_id == "gpt-5"


def test_build_model_catalog_merge_key_case_insensitive() -> None:
    assert build_model_catalog_merge_key("OpenAI", "GPT-5") == "openai::gpt-5"


def test_is_cloud_model_ref() -> None:
    assert is_cloud_model_ref("openai/gpt-5:cloud") is True
    assert is_cloud_model_ref("openai/gpt-5:local") is False
    assert is_cloud_model_ref("openai/gpt-5") is False
    # Double-suffixed refs are ambiguous, not cloud refs.
    assert is_cloud_model_ref("x:cloud:cloud") is False
    assert is_cloud_model_ref(None) is False
    assert is_cloud_model_ref("   ") is False
