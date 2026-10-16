"""External price-feed normalization (OpenRouter/upstream shapes → catalog costs).

OpenClaw parity:
``packages/model-catalog-core/src/model-catalog-pricing.ts``.
Unavailable prices stay distinct from malformed feeds: a feed with a
duplicate id or an unparseable required rate invalidates the whole
feed (returns ``None``) instead of publishing partial prices. An
empty feed establishes nothing and also yields ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Literal

from jarvis_normalization_core.number_coerce import (
    as_finite_number_in_range,
    as_non_negative_finite_number,
    as_positive_safe_integer,
    parse_strict_finite_number,
)
from jarvis_normalization_core.string_coerce import (
    as_optional_record,
    normalize_optional_string,
    normalize_trimmed_string_list,
)

from .model_catalog_refs import normalize_provider_id as normalize_model_catalog_provider_id
from .model_catalog_types import ModelCatalogCost, ModelCatalogTieredCost

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
LITELLM_PRICING_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)


@dataclass(frozen=True, slots=True)
class ModelPricingSourceMeta:
    """One published price-feed source."""

    id: str
    label: str
    url: str
    authoritative: bool


MODEL_PRICING_SOURCES: tuple[ModelPricingSourceMeta, ...] = (
    ModelPricingSourceMeta(
        id="openCode",
        label="OpenCode",
        url="https://models.opencode.ai/api.json",
        authoritative=True,
    ),
    ModelPricingSourceMeta(
        id="venice",
        label="Venice",
        url="https://api.venice.ai/api/v1/models",
        authoritative=True,
    ),
    ModelPricingSourceMeta(
        id="chutes",
        label="Chutes",
        url="https://llm.chutes.ai/v1/models",
        authoritative=True,
    ),
    ModelPricingSourceMeta(
        id="cerebras",
        label="Cerebras",
        url="https://api.cerebras.ai/public/v1/models",
        authoritative=True,
    ),
    ModelPricingSourceMeta(
        id="deepinfra",
        label="DeepInfra",
        url="https://api.deepinfra.com/models/list",
        authoritative=True,
    ),
    ModelPricingSourceMeta(
        id="openRouter",
        label="OpenRouter",
        url=OPENROUTER_MODELS_URL,
        authoritative=False,
    ),
    ModelPricingSourceMeta(
        id="liteLLM",
        label="LiteLLM",
        url=LITELLM_PRICING_URL,
        authoritative=False,
    ),
)

ModelPricingSourceId = Literal[
    "openCode", "venice", "chutes", "cerebras", "deepinfra", "openRouter", "liteLLM"
]


@dataclass(frozen=True, slots=True)
class ModelPricingSource:
    """Per-source policy for one provider."""

    provider: str | None = None
    passthrough_provider_model: bool = False
    model_id_transforms: tuple[Literal["version-dots"], ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class CompleteModelCost:
    """A fully-specified four-rate cost with optional context tiers."""

    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0
    tiered_pricing: tuple[ModelCatalogTieredCost, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ContextPrice:
    """One context-tier price point."""

    size: int = 0
    cost: CompleteModelCost | None = None


def normalize_model_pricing_provider(value: Any) -> dict[str, Any] | None:
    """Normalize source policy without deciding which plugin owns the provider."""
    record = as_optional_record(value)
    if record is None:
        return None
    policy: dict[str, Any] = {}
    if isinstance(record.get("external"), bool):
        policy["external"] = record["external"]
    for source in MODEL_PRICING_SOURCES:
        raw = record.get(source.id)
        if raw is False:
            policy[source.id] = False
            continue
        row = as_optional_record(raw)
        configured_provider = (
            normalize_optional_string(row.get("provider")) if row is not None else None
        )
        provider = normalize_model_catalog_provider_id(configured_provider or "")
        transforms = (
            [
                entry
                for entry in normalize_trimmed_string_list(row.get("modelIdTransforms"))
                if entry == "version-dots"
            ]
            if row is not None
            else []
        )
        entry: dict[str, Any] = {}
        if provider:
            entry["provider"] = provider
        if row is not None and row.get("passthroughProviderModel") is True:
            entry["passthroughProviderModel"] = True
        if transforms:
            entry["modelIdTransforms"] = transforms
        if entry:
            policy[source.id] = entry
    return policy or None


def normalize_model_pricing_catalog(
    rows: Any,
    normalize_pricing: Callable[[Any], CompleteModelCost | None],
    *,
    read_model_id: Callable[[dict[str, Any]], Any] | None = None,
    read_pricing: Callable[[dict[str, Any]], Any] | None = None,
    is_supported_pricing: Callable[[Any], bool] | None = None,
) -> dict[str, CompleteModelCost] | None:
    """Normalize one price feed into id-keyed costs.

    A duplicate id or an unparseable required rate invalidates the
    whole feed. Models without pricing are skipped; declared rates
    are validated even when their qualifications are unrepresentable
    (only supported ones are published).
    """
    if not isinstance(rows, list):
        return None
    prices: dict[str, CompleteModelCost] = {}
    seen: set[str] = set()
    for value in rows:
        model = as_optional_record(value)
        model_id = (
            normalize_optional_string(
                read_model_id(model) if read_model_id is not None else model.get("id")
            )
            if model is not None
            else None
        )
        if model is None or not model_id or model_id in seen:
            return None
        seen.add(model_id)
        if read_pricing is None:
            # Absent pricing is skipped; explicit null flows into the
            # normalizer and invalidates the feed (TS `undefined` vs `null`).
            if "pricing" not in model:
                continue
            raw_pricing = model["pricing"]
        else:
            raw_pricing = read_pricing(model)
            if raw_pricing is None:
                continue
        pricing = normalize_pricing(raw_pricing)
        if pricing is None:
            return None
        supported = is_supported_pricing(raw_pricing) if is_supported_pricing else True
        if supported:
            prices[model_id] = pricing
    # An empty price feed cannot establish that every known price disappeared.
    return prices or None


def _read_pricing_cost(
    value: Any, source: Literal["openRouter", "upstream"]
) -> CompleteModelCost | None:
    row = as_optional_record(value)
    per_token = source == "openRouter"
    keys = (
        ("prompt", "completion", "input_cache_read", "input_cache_write")
        if per_token
        else ("input", "output", "cache_read", "cache_write")
    )
    rates: list[float] = []
    for index, key in enumerate(keys):
        present = row is not None and key in row
        raw = row.get(key) if row is not None else None
        # Missing cache rates mean no cache charge. An explicit null is
        # not missing — it must invalidate, exactly like TS `undefined`
        # vs `null` handling.
        if index >= 2 and not present:
            rates.append(0.0)
            continue
        rate = parse_strict_finite_number(raw) if per_token else as_non_negative_finite_number(raw)
        if rate is None:
            return None
        scaled = as_non_negative_finite_number(rate * (1_000_000 if per_token else 1))
        if scaled is None:
            return None
        rates.append(float(scaled))
    cost_input, cost_output, cache_read, cache_write = rates
    return CompleteModelCost(
        input=cost_input, output=cost_output, cache_read=cache_read, cache_write=cache_write
    )


def _with_context_prices(
    cost: CompleteModelCost | None, tiers: list[ContextPrice]
) -> CompleteModelCost | None:
    if cost is None:
        return None
    ordered = sorted(tiers, key=lambda tier: tier.size)
    if not ordered:
        return cost
    first = ordered[0]
    tiered = [
        ModelCatalogTieredCost(
            input=cost.input,
            output=cost.output,
            cache_read=cost.cache_read,
            cache_write=cost.cache_write,
            cost_range=(0, first.size),
        )
    ]
    for index, tier in enumerate(ordered):
        # A recognized context tier with unknown rates invalidates the
        # price, not just that tier.
        if tier.cost is None:
            return None
        following = ordered[index + 1].size if index + 1 < len(ordered) else None
        # Conflicting thresholds cannot select one whole-request price;
        # never publish zero-width tiers.
        if following == tier.size:
            return None
        span = (tier.size, following) if following is not None else (tier.size,)
        tiered.append(
            ModelCatalogTieredCost(
                input=tier.cost.input,
                output=tier.cost.output,
                cache_read=tier.cost.cache_read,
                cache_write=tier.cost.cache_write,
                cost_range=span,
            )
        )
    return replace(cost, tiered_pricing=tuple(tiered))


# OpenRouter's /models price keys include charge dimensions outside our four
# token rates. Keep this closed so unknown predicates cannot silently become
# unconditional prices.
_OPENROUTER_PRICE_FIELDS = frozenset(
    {
        "prompt",
        "completion",
        "request",
        "image",
        "web_search",
        "internal_reasoning",
        "input_cache_read",
        "input_cache_write",
        "audio",
        "input_audio_cache",
        "input_cache_write_1h",
        "image_output",
        "audio_output",
    }
)


def normalize_open_router_model_pricing(value: Any) -> CompleteModelCost | None:
    """Read native OpenRouter per-token prices and static prompt-length overrides."""
    row = as_optional_record(value)
    overrides: list[tuple[int, dict[str, Any]]] = []
    raw_overrides = row.get("overrides") if row is not None else None
    for raw in raw_overrides if isinstance(raw_overrides, list) else []:
        override = as_optional_record(raw)
        # All predicates must match; UTC schedules and unknown conditions
        # are not static tiers.
        if override is None or any(
            key != "min_prompt_tokens" and key not in _OPENROUTER_PRICE_FIELDS for key in override
        ):
            continue
        threshold = as_finite_number_in_range(
            override.get("min_prompt_tokens"), min=0, max=2**53 - 1, max_exclusive=True
        )
        if threshold is not None:
            overrides.append((int(threshold) + 1, override))
    # Token counts are integral and thresholds strict. Resolve every boundary
    # from the native base, then apply matching overrides per key in their
    # original source order.
    sizes = sorted({size for size, _ in overrides})
    base = dict(row) if row is not None else {}
    tiers = []
    for size in sizes:
        prices: dict[str, Any] = dict(base)
        for override_size, override in overrides:
            if size >= override_size:
                prices.update(override)
        tiers.append(ContextPrice(size=size, cost=_read_pricing_cost(prices, "openRouter")))
    return _with_context_prices(_read_pricing_cost(value, "openRouter"), tiers)


def normalize_upstream_model_pricing(value: Any) -> CompleteModelCost | None:
    """Read upstream per-million prices, preferring context tiers over context_over_200k."""
    row = as_optional_record(value)
    tiers: list[ContextPrice] = []
    raw_tiers = row.get("tiers") if row is not None else None
    for raw in raw_tiers if isinstance(raw_tiers, list) else []:
        price = as_optional_record(raw)
        tier = as_optional_record(price.get("tier")) if price is not None else None
        size = as_positive_safe_integer(tier.get("size")) if tier is not None else None
        if tier is not None and tier.get("type") == "context" and size:
            tiers.append(ContextPrice(size=size, cost=_read_pricing_cost(price, "upstream")))
    legacy_raw = row.get("context_over_200k") if row is not None else None
    if not tiers and as_optional_record(legacy_raw) is not None:
        # An empty legacy object still declares a tier with unknown rates,
        # which invalidates the price (it is not silently ignored).
        tiers.append(ContextPrice(size=200_000, cost=_read_pricing_cost(legacy_raw, "upstream")))
    return _with_context_prices(_read_pricing_cost(value, "upstream"), tiers)


def complete_cost_to_catalog_cost(cost: CompleteModelCost) -> ModelCatalogCost:
    """Project a fully-specified cost onto the catalog cost shape."""
    return ModelCatalogCost(
        input=cost.input,
        output=cost.output,
        cache_read=cost.cache_read,
        cache_write=cost.cache_write,
        tiered_pricing=cost.tiered_pricing,
    )


__all__ = [
    "ContextPrice",
    "CompleteModelCost",
    "LITELLM_PRICING_URL",
    "MODEL_PRICING_SOURCES",
    "ModelPricingSource",
    "ModelPricingSourceId",
    "ModelPricingSourceMeta",
    "OPENROUTER_MODELS_URL",
    "complete_cost_to_catalog_cost",
    "normalize_model_pricing_catalog",
    "normalize_model_pricing_provider",
    "normalize_open_router_model_pricing",
    "normalize_upstream_model_pricing",
]
