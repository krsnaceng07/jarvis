"""Parity tests for catalog normalization.

Mirrors ``model-catalog-normalize.ts`` and its test vectors: malformed
fields are dropped (never guessed), provider fallbacks fill row gaps,
rows sort by (provider, id), and owned-provider gating applies.
"""

from __future__ import annotations

from jarvis_model_catalog import (
    ModelCatalogProvider,
    normalize_model_catalog,
    normalize_model_catalog_model,
    normalize_model_catalog_provider_rows,
)


def test_model_requires_id() -> None:
    assert normalize_model_catalog_model({"name": "x"}) is None
    assert normalize_model_catalog_model("nope") is None
    model = normalize_model_catalog_model({"id": " gpt-5 "})
    assert model is not None
    assert model.id == "gpt-5"


def test_model_drops_malformed_fields() -> None:
    model = normalize_model_catalog_model(
        {
            "id": "m",
            "api": "bogus-api",
            "input": ["text", "bogus"],
            "reasoning": "yes",
            "contextWindow": -5,
            "status": "bogus",
            "tags": ["a", 42, " "],
        }
    )
    assert model is not None
    assert model.api is None
    assert model.input == ("text",)
    assert model.reasoning is None
    assert model.context_window is None
    assert model.status is None
    assert model.tags == ("a",)


def test_model_compat_and_cost() -> None:
    model = normalize_model_catalog_model(
        {
            "id": "m",
            "cost": {"input": 1.5, "output": 2, "bogus": 1},
            "compat": {
                "supportsStore": True,
                "supportsTemperature": "yes",
                "codeMode": "preferred",
                "maxTokensField": "max_tokens",
                "thinkingFormat": "deepseek",
                "reasoningEffortMap": {"high": "max", "x": "  "},
            },
        }
    )
    assert model is not None
    assert model.cost is not None
    assert model.cost.input == 1.5
    assert model.cost.output == 2.0
    assert model.compat is not None
    assert model.compat.supports_store is True
    assert model.compat.supports_temperature is None
    assert model.compat.code_mode == "preferred"
    assert model.compat.max_tokens_field == "max_tokens"
    assert model.compat.thinking_format == "deepseek"
    assert model.compat.reasoning_effort_map == {"high": "max"}


def test_provider_rows_fallbacks_and_sort() -> None:
    raw_models: list[object] = [
        {"id": "b-model"},
        {"id": "a-model", "api": "anthropic-messages", "reasoning": True},
        {"name": "nameless-has-no-id"},
    ]
    models = tuple(
        model for raw in raw_models if (model := normalize_model_catalog_model(raw)) is not None
    )
    provider = ModelCatalogProvider(
        models=models,
        api="openai-responses",
        base_url="https://api.example.com",
        headers={"x-a": "b"},
    )
    rows = normalize_model_catalog_provider_rows("OpenAI", provider, "manifest")
    assert [row.id for row in rows] == ["a-model", "b-model"]
    first, second = rows
    # Row-level api wins; provider api fills the gap.
    assert first.api == "anthropic-messages"
    assert second.api == "openai-responses"
    # Base URL + headers fall back from the provider.
    assert second.base_url == "https://api.example.com"
    assert second.headers == {"x-a": "b"}
    # Join identity + resolved defaults.
    assert second.ref == "openai/b-model"
    assert second.merge_key == "openai::b-model"
    assert second.name == "b-model"
    assert second.input == ("text",)
    assert second.reasoning is False
    assert second.status == "available"
    assert first.reasoning is True


def test_catalog_owned_provider_gating() -> None:
    catalog = normalize_model_catalog(
        {
            "providers": {
                "openai": {"models": [{"id": "gpt-5"}]},
                "stranger": {"models": [{"id": "x"}]},
            },
            "aliases": {"oai": {"provider": "openai"}, "bad": {"provider": "stranger"}},
            "discovery": {"openai": "static", "stranger": "static", "x": "bogus"},
            "suppressions": [{"provider": "openai", "model": "old"}],
            "runtimeAugment": True,
        },
        {"OpenAI"},
    )
    assert catalog is not None
    assert set(catalog.providers) == {"openai"}
    assert set(catalog.aliases) == {"oai"}
    assert catalog.discovery == {"openai": "static"}
    assert len(catalog.suppressions) == 1
    assert catalog.runtime_augment is True


def test_catalog_empty_when_nothing_owned() -> None:
    assert normalize_model_catalog({"providers": {"x": {"models": []}}}, {"y"}) is None
    assert normalize_model_catalog("nope", {"x"}) is None


def test_suppression_explicit_when_null_drops_retirement() -> None:
    # Explicit `when: null` counts as present: with a retirement the rule
    # drops instead of broadening the repair.
    assert (
        normalize_model_catalog(
            {
                "suppressions": [
                    {
                        "provider": "openai",
                        "model": "old",
                        "retirement": {"replacedBy": "new"},
                        "when": None,
                    }
                ]
            },
            set(),
        )
        is None
    )
    # Without a retirement, `when: null` is harmless and the rule keeps.
    catalog = normalize_model_catalog(
        {"suppressions": [{"provider": "openai", "model": "old", "when": None}]},
        set(),
    )
    assert catalog is not None
    assert len(catalog.suppressions) == 1


def test_sort_partition_null_preserved_blank_omitted() -> None:
    model = normalize_model_catalog_model(
        {
            "id": "m",
            "compat": {
                "openRouterRouting": {
                    "sort": {"by": "price", "partition": None},
                },
            },
        }
    )
    assert model is not None
    assert model.compat is not None
    routing = model.compat.open_router_routing
    assert routing is not None
    assert routing.sort == {"by": "price", "partition": None}
    bare = normalize_model_catalog_model(
        {"id": "m", "compat": {"openRouterRouting": {"sort": {"by": "price"}}}}
    )
    assert bare is not None
    assert bare.compat is not None
    bare_routing = bare.compat.open_router_routing
    assert bare_routing is not None
    assert bare_routing.sort == {"by": "price"}


def test_suppression_retirement_scope_guard() -> None:
    # Malformed retirement scope must never broaden the repair: dropped.
    catalog = normalize_model_catalog(
        {
            "suppressions": [
                {
                    "provider": "openai",
                    "model": "old",
                    "retirement": {"replacedBy": "new"},
                    "when": {"baseUrlHosts": [42]},
                }
            ]
        },
        set(),
    )
    assert catalog is None
