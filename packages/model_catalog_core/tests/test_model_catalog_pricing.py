"""Parity tests for price-feed normalization.

Mirrors ``model-catalog-pricing.ts`` vectors: whole-feed invalidation
on duplicates/unparseable rates, empty-feed silence, OpenRouter
per-token scaling with prompt-length tiers, upstream context tiers.
"""

from __future__ import annotations

from jarvis_model_catalog import (
    CompleteModelCost,
    normalize_model_pricing_catalog,
    normalize_model_pricing_provider,
    normalize_open_router_model_pricing,
    normalize_upstream_model_pricing,
)


def test_pricing_provider_policy() -> None:
    policy = normalize_model_pricing_provider(
        {"external": True, "openRouter": False, "liteLLM": {"provider": "LiteLLM "}}
    )
    assert policy == {
        "external": True,
        "openRouter": False,
        "liteLLM": {"provider": "litellm"},
    }
    assert normalize_model_pricing_provider({}) is None
    assert normalize_model_pricing_provider(None) is None


def _flat_cost(value: object) -> CompleteModelCost | None:
    if not isinstance(value, dict):
        return None
    cost_input = value.get("input")
    cost_output = value.get("output")
    if not isinstance(cost_input, (int, float)) or not isinstance(cost_output, (int, float)):
        return None
    return CompleteModelCost(input=float(cost_input), output=float(cost_output))


def test_pricing_catalog_happy_path() -> None:
    prices = normalize_model_pricing_catalog(
        [{"id": "a", "pricing": {"input": 1, "output": 2}}, {"id": "b"}],
        _flat_cost,
    )
    assert prices is not None
    assert set(prices) == {"a"}
    assert prices["a"].input == 1.0


def test_pricing_catalog_invalidates_whole_feed() -> None:
    # Unparseable required rate invalidates the feed.
    assert (
        normalize_model_pricing_catalog(
            [{"id": "a", "pricing": {"input": "bogus", "output": 2}}], _flat_cost
        )
        is None
    )
    # Duplicate id invalidates the feed.
    assert normalize_model_pricing_catalog([{"id": "a"}, {"id": "a"}], _flat_cost) is None
    # Empty feed establishes nothing.
    assert normalize_model_pricing_catalog([], _flat_cost) is None


def test_null_is_not_missing() -> None:
    # Absent cache rates mean free; explicit null invalidates (TS null vs undefined).
    assert (
        normalize_open_router_model_pricing(
            {"prompt": "0.000001", "completion": "0.000002", "input_cache_read": None}
        )
        is None
    )
    assert normalize_model_pricing_catalog([{"id": "a", "pricing": None}], _flat_cost) is None
    assert (
        normalize_model_pricing_catalog(
            [{"id": "a"}, {"id": "b", "pricing": {"input": 1, "output": 2}}],
            _flat_cost,
        )
        is not None
    )


def test_empty_legacy_context_tier_invalidates() -> None:
    assert (
        normalize_upstream_model_pricing({"input": 1, "output": 2, "context_over_200k": {}}) is None
    )


def test_open_router_per_token_scaling() -> None:
    cost = normalize_open_router_model_pricing({"prompt": "0.000001", "completion": "0.000002"})
    assert cost is not None
    assert cost.input == 1.0
    assert cost.output == 2.0
    assert cost.cache_read == 0.0
    # Missing required rate invalidates.
    assert normalize_open_router_model_pricing({"prompt": "1"}) is None


def test_open_router_prompt_length_tiers() -> None:
    cost = normalize_open_router_model_pricing(
        {
            "prompt": "0.000001",
            "completion": "0.000002",
            "overrides": [{"min_prompt_tokens": 128000, "prompt": "0.000002"}],
        }
    )
    assert cost is not None
    assert len(cost.tiered_pricing) == 2
    base, tier = cost.tiered_pricing
    assert base.cost_range == (0, 128001)
    assert tier.cost_range == (128001,)
    assert tier.input == 2.0


def test_upstream_context_tiers() -> None:
    cost = normalize_upstream_model_pricing(
        {
            "input": 1,
            "output": 2,
            "tiers": [
                {"tier": {"type": "context", "size": 200000}, "input": 2, "output": 4},
            ],
        }
    )
    assert cost is not None
    assert cost.input == 1.0
    assert len(cost.tiered_pricing) == 2
    assert cost.tiered_pricing[1].cost_range == (200000,)
    # Legacy context_over_200k fallback.
    legacy = normalize_upstream_model_pricing(
        {"input": 1, "output": 2, "context_over_200k": {"input": 2, "output": 4}}
    )
    assert legacy is not None
    assert len(legacy.tiered_pricing) == 2
