"""Parity tests for catalog types, context windows, configured refs, bundles."""

from __future__ import annotations

import pytest
from jarvis_model_catalog import (
    MODEL_CATALOG_APIS,
    ModelCatalogThinkingLevelMap,
    RemoteCatalogError,
    collect_configured_model_ref_values,
    collect_configured_model_refs,
    is_model_catalog_thinking_format,
    list_model_refs_from_config_value,
    normalize_model_catalog_context_window_selection,
    parse_remote_model_catalog_bundle,
    sanitize_remote_model_catalog_bundle,
    validate_and_sanitize_remote_model_catalog_bundle,
)


def test_api_vocabulary() -> None:
    assert "anthropic-messages" in MODEL_CATALOG_APIS
    assert "openai-responses" in MODEL_CATALOG_APIS


def test_barrel_exports_thinking_level_map() -> None:
    levels: ModelCatalogThinkingLevelMap = {"high": "max"}
    assert levels["high"] == "max"


def test_thinking_format_guard() -> None:
    assert is_model_catalog_thinking_format("deepseek") is True
    assert is_model_catalog_thinking_format("other") is False


def test_context_window_selection_atomic() -> None:
    good = normalize_model_catalog_context_window_selection(
        {
            "contextWindows": [
                {"id": "big", "label": "Big", "contextWindow": 200000},
                {"id": "small", "label": "Small", "contextWindow": 64000},
            ],
            "contextWindowDefault": "small",
        }
    )
    assert good["contextWindowDefault"] == "small"
    assert [o.id for o in good["contextWindows"]] == ["small", "big"]
    # Invalid default drops the whole option list.
    assert (
        normalize_model_catalog_context_window_selection(
            {
                "contextWindows": [{"id": "a", "label": "A", "contextWindow": 1}],
                "contextWindowDefault": "missing",
            }
        )
        == {}
    )
    # Integer-valued floats are valid (TS Number.isInteger parity).
    floated = normalize_model_catalog_context_window_selection(
        {
            "contextWindows": [{"id": "a", "label": "A", "contextWindow": 131072.0}],
            "contextWindowDefault": "a",
        }
    )
    assert floated["contextWindows"][0].context_window == 131072
    # Duplicates, empties, and non-records are skipped.
    assert (
        normalize_model_catalog_context_window_selection(
            {
                "contextWindows": [
                    {"id": "a", "label": "A", "contextWindow": 1},
                    {"id": "a", "label": "A2", "contextWindow": 2},
                    {"id": "", "label": "B", "contextWindow": 2},
                    "nope",
                ],
                "contextWindowDefault": "a",
            }
        )["contextWindows"]
        != []
    )


def test_configured_refs_collection() -> None:
    config = {
        "agents": {
            "defaults": {"model": "openai/gpt-5"},
            "entries": {"a": {"model": {"primary": "x/y", "fallbacks": ["z/w"]}}},
        },
        "channels": {"modelByChannel": {"telegram": {"123": "anthropic/claude"}}},
    }
    values = collect_configured_model_ref_values(config)
    assert values == ["openai/gpt-5", "x/y", "z/w", "anthropic/claude"]
    refs = collect_configured_model_refs(config)
    assert refs[0].path == "agents.defaults.model"


def test_list_model_refs_from_selector() -> None:
    assert list_model_refs_from_config_value("a/b") == ["a/b"]
    assert list_model_refs_from_config_value({"primary": "a/b", "fallbacks": ["c/d", 42]}) == [
        "a/b",
        "c/d",
    ]
    assert list_model_refs_from_config_value(None) == []


def _bundle(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schemaVersion": 1,
        "generatedAt": 1_700_000_000_000,
        "sourceCommit": "abc123",
        "providers": {
            "openai": {
                "models": [
                    {
                        "id": "gpt-5",
                        "api": "openai-responses",
                        "baseUrl": "https://api.openai.com",
                        "headers": {"x-a": "b"},
                    }
                ]
            }
        },
    }
    base.update(overrides)
    return base


def test_remote_bundle_validate_and_sanitize_strips_transport() -> None:
    bundle = validate_and_sanitize_remote_model_catalog_bundle(_bundle())
    provider = bundle.providers["openai"]
    assert isinstance(provider, dict)
    assert "baseUrl" not in provider
    assert "headers" not in provider["models"][0]
    assert provider["models"][0]["id"] == "gpt-5"


def test_remote_bundle_rejects_bad_shapes() -> None:
    with pytest.raises(RemoteCatalogError):
        parse_remote_model_catalog_bundle({**_bundle(), "schemaVersion": 2})
    with pytest.raises(RemoteCatalogError):
        parse_remote_model_catalog_bundle(
            {
                **_bundle(),
                "providers": {"p": {"models": [{"id": "a"}, {"id": "a"}]}},
            }
        )
    with pytest.raises(RemoteCatalogError):
        parse_remote_model_catalog_bundle(
            {
                **_bundle(),
                "providers": {
                    "p": {
                        "models": [
                            {
                                "id": "a",
                                "contextWindows": [{"id": "w", "label": "W", "contextWindow": 1}],
                                "contextWindowDefault": "missing",
                            }
                        ]
                    }
                },
            }
        )
    with pytest.raises(RemoteCatalogError):
        parse_remote_model_catalog_bundle({**_bundle(), "generatedAt": 9_999_999_999_999_999})


def test_sanitize_is_transport_only() -> None:
    parsed = parse_remote_model_catalog_bundle(_bundle())
    sanitized = sanitize_remote_model_catalog_bundle(parsed)
    assert sanitized.source_commit == "abc123"
    assert sanitized.generated_at == parsed.generated_at
