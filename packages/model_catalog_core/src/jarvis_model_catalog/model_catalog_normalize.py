"""Raw provider catalogs → stable normalized rows for lookup and merging.

OpenClaw parity:
``packages/model-catalog-core/src/model-catalog-normalize.ts``.
Every field is validated and dropped when malformed (never coerced
into a guess); only fully-valid models become rows. Provider-level
``api``/``baseUrl``/``headers`` fall back to row level, and rows
sort deterministically by ``(provider, id)``.
"""

from __future__ import annotations

from typing import Any, cast

from jarvis_normalization_core.number_coerce import (
    as_finite_number,
    as_non_negative_finite_number,
    as_positive_finite_number,
)
from jarvis_normalization_core.string_coerce import (
    as_optional_record,
    normalize_optional_string,
    normalize_optional_trimmed_string_list,
    normalize_trimmed_string_list,
)

from .context_windows import normalize_model_catalog_context_window_selection
from .model_catalog_refs import build_model_catalog_merge_key, build_model_catalog_ref
from .model_catalog_types import (
    MODEL_CATALOG_APIS,
    MODEL_CATALOG_THINKING_LEVELS,
    ModelCatalog,
    ModelCatalogAlias,
    ModelCatalogApi,
    ModelCatalogCompatConfig,
    ModelCatalogCost,
    ModelCatalogDiscovery,
    ModelCatalogImageInputConfig,
    ModelCatalogInput,
    ModelCatalogMediaInputConfig,
    ModelCatalogModel,
    ModelCatalogOpenRouterRouting,
    ModelCatalogProvider,
    ModelCatalogSource,
    ModelCatalogStatus,
    ModelCatalogSuppression,
    ModelCatalogSuppressionRetirement,
    ModelCatalogSuppressionWhen,
    ModelCatalogTieredCost,
    ModelCatalogVercelGatewayRouting,
    NormalizedModelCatalogRow,
    is_model_catalog_thinking_format,
)
from .provider_id import normalize_provider_id

_MODEL_CATALOG_INPUTS = frozenset({"text", "image", "document"})
_MODEL_CATALOG_DISCOVERY_MODES = frozenset({"static", "refreshable", "runtime"})
_MODEL_CATALOG_STATUSES = frozenset({"available", "preview", "deprecated", "disabled"})
_MODEL_CATALOG_API_SET = frozenset(MODEL_CATALOG_APIS)
_DEFAULT_MODEL_INPUT: tuple[ModelCatalogInput, ...] = ("text",)
_DEFAULT_MODEL_STATUS: ModelCatalogStatus = "available"

_BLOCKED_OBJECT_KEYS = frozenset({"__proto__", "prototype", "constructor"})


def _is_blocked_object_key(key: str) -> bool:
    """Reject keys that could mutate prototypes when copied into records."""
    return key in _BLOCKED_OBJECT_KEYS


def _normalize_positive_integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and value.is_integer() and value > 0:
        result = int(value)
        return result
    return None


def _normalize_thinking_level_map(value: Any) -> dict[str, str | None] | None:
    record = as_optional_record(value)
    if record is None:
        return None
    normalized: dict[str, str | None] = {}
    for level in MODEL_CATALOG_THINKING_LEVELS:
        raw = record.get(level)
        if raw is None:
            # Explicit null marks the level unsupported (distinct from absent).
            if level in record:
                normalized[level] = None
            continue
        text = normalize_optional_string(raw)
        if text is not None:
            normalized[level] = text
    return normalized or None


def _normalize_safe_record_key(value: Any) -> str:
    key = normalize_optional_string(value) or ""
    return key if key and not _is_blocked_object_key(key) else ""


def _normalize_owned_provider_set(providers: set[str] | frozenset[str]) -> frozenset[str]:
    return frozenset(normalized for p in providers if (normalized := normalize_provider_id(p)))


def _normalize_string_map(value: Any) -> dict[str, str] | None:
    record = as_optional_record(value)
    if record is None:
        return None
    normalized: dict[str, str] = {}
    for raw_key, raw_value in record.items():
        key = _normalize_safe_record_key(raw_key)
        map_value = normalize_optional_string(raw_value) or ""
        if key and map_value:
            normalized[key] = map_value
    return normalized or None


def _merge_string_maps(
    base: dict[str, str] | None, override: dict[str, str] | None
) -> dict[str, str] | None:
    if not base and not override:
        return None
    return {**(base or {}), **(override or {})}


def _normalize_model_catalog_api(value: Any) -> ModelCatalogApi | None:
    api = normalize_optional_string(value) or ""
    # Membership-tested against the closed vocabulary before casting.
    return cast(ModelCatalogApi, api) if api in _MODEL_CATALOG_API_SET else None


def _normalize_model_catalog_inputs(value: Any) -> list[ModelCatalogInput] | None:
    inputs: list[ModelCatalogInput] = [
        cast(ModelCatalogInput, entry)
        for entry in normalize_trimmed_string_list(value)
        if entry in _MODEL_CATALOG_INPUTS
    ]
    return inputs or None


def _normalize_tiered_cost(value: Any) -> list[ModelCatalogTieredCost] | None:
    if not isinstance(value, list):
        return None
    rows: list[Any] = value
    normalized: list[ModelCatalogTieredCost] = []
    for entry in rows:
        record = as_optional_record(entry)
        span = record.get("range") if record is not None else None
        if record is None or not isinstance(span, list) or not 1 <= len(span) <= 2:
            continue
        cost_input = as_non_negative_finite_number(record.get("input"))
        cost_output = as_non_negative_finite_number(record.get("output"))
        cache_read = as_non_negative_finite_number(record.get("cacheRead"))
        cache_write = as_non_negative_finite_number(record.get("cacheWrite"))
        range_values = [as_non_negative_finite_number(item) for item in span]
        if (
            cost_input is None
            or cost_output is None
            or cache_read is None
            or cache_write is None
            or any(item is None for item in range_values)
        ):
            continue
        values: list[float] = [float(item) for item in range_values if item is not None]
        normalized.append(
            ModelCatalogTieredCost(
                input=float(cost_input),
                output=float(cost_output),
                cache_read=float(cache_read),
                cache_write=float(cache_write),
                cost_range=tuple(values),
            )
        )
    return normalized or None


def _normalize_cost(value: Any) -> ModelCatalogCost | None:
    record = as_optional_record(value)
    if record is None:
        return None
    cost_input = as_non_negative_finite_number(record.get("input"))
    cost_output = as_non_negative_finite_number(record.get("output"))
    cache_read = as_non_negative_finite_number(record.get("cacheRead"))
    cache_write = as_non_negative_finite_number(record.get("cacheWrite"))
    tiered = _normalize_tiered_cost(record.get("tieredPricing"))
    fields: dict[str, Any] = {}
    if cost_input is not None:
        fields["input"] = float(cost_input)
    if cost_output is not None:
        fields["output"] = float(cost_output)
    if cache_read is not None:
        fields["cache_read"] = float(cache_read)
    if cache_write is not None:
        fields["cache_write"] = float(cache_write)
    if tiered is not None:
        fields["tiered_pricing"] = tuple(tiered)
    return ModelCatalogCost(**fields) if fields else None


def _normalize_open_router_price(value: Any) -> dict[str, float | str] | None:
    record = as_optional_record(value)
    if record is None:
        return None
    price: dict[str, float | str] = {}
    for key in ("prompt", "completion", "image", "audio", "request"):
        candidate = record.get(key)
        text = normalize_optional_string(candidate)
        number = as_finite_number(candidate)
        if text is not None:
            price[key] = text
        elif number is not None:
            price[key] = float(number)
    return price or None


def _normalize_open_router_metric(value: Any) -> float | dict[str, float] | None:
    number = as_finite_number(value)
    if number is not None:
        return float(number)
    record = as_optional_record(value)
    if record is None:
        return None
    metric: dict[str, float] = {}
    for key in ("p50", "p75", "p90", "p99"):
        cutoff = as_finite_number(record.get(key))
        if cutoff is not None:
            metric[key] = float(cutoff)
    return metric or None


def _normalize_open_router_sort(value: Any) -> str | dict[str, Any] | None:
    text = normalize_optional_string(value)
    if text:
        return text
    record = as_optional_record(value)
    if record is None:
        return None
    by = normalize_optional_string(record.get("by"))
    sort: dict[str, Any] = {}
    if by:
        sort["by"] = by
    if "partition" in record:
        # Explicit null is preserved (TS `partition: null`); missing or
        # blank partitions are omitted.
        raw_partition = record["partition"]
        if raw_partition is None:
            sort["partition"] = None
        else:
            partition = normalize_optional_string(raw_partition)
            if partition is not None:
                sort["partition"] = partition
    return sort or None


def _normalize_open_router_routing(value: Any) -> ModelCatalogOpenRouterRouting | None:
    record = as_optional_record(value)
    if record is None:
        return None
    fields: dict[str, Any] = {}
    for key in ("allow_fallbacks", "require_parameters", "zdr", "enforce_distillable_text"):
        raw = record.get(key)
        if isinstance(raw, bool):
            fields[key] = raw
    data_collection = record.get("data_collection")
    if data_collection in ("deny", "allow"):
        fields["data_collection"] = data_collection
    for key in ("order", "only", "ignore", "quantizations"):
        items = normalize_optional_trimmed_string_list(record.get(key))
        if items:
            fields[key] = tuple(items)
    sort = _normalize_open_router_sort(record.get("sort"))
    if sort:
        fields["sort"] = sort
    max_price = _normalize_open_router_price(record.get("max_price"))
    if max_price:
        fields["max_price"] = max_price
    for key in ("preferred_min_throughput", "preferred_max_latency"):
        metric = _normalize_open_router_metric(record.get(key))
        if metric is not None:
            fields[key] = metric
    return ModelCatalogOpenRouterRouting(**fields) if fields else None


def _normalize_vercel_gateway_routing(value: Any) -> ModelCatalogVercelGatewayRouting | None:
    record = as_optional_record(value)
    if record is None:
        return None
    fields: dict[str, Any] = {}
    for key in ("only", "order"):
        items = normalize_optional_trimmed_string_list(record.get(key))
        if items:
            fields[key] = tuple(items)
    return ModelCatalogVercelGatewayRouting(**fields) if fields else None


_TS_TO_PY_COMPAT_FIELDS = {
    "supportsStore": "supports_store",
    "supportsPromptCacheKey": "supports_prompt_cache_key",
    "supportsDeveloperRole": "supports_developer_role",
    "supportsReasoningEffort": "supports_reasoning_effort",
    "supportsTemperature": "supports_temperature",
    "supportsInstructions": "supports_instructions",
    "supportsUsageInStreaming": "supports_usage_in_streaming",
    "supportsTools": "supports_tools",
    "supportsStrictMode": "supports_strict_mode",
    "supportsJsonSchemaResponseFormat": "supports_json_schema_response_format",
    "requiresStringContent": "requires_string_content",
    "strictMessageKeys": "strict_message_keys",
    "requiresToolResultName": "requires_tool_result_name",
    "requiresAssistantAfterToolResult": "requires_assistant_after_tool_result",
    "requiresThinkingAsText": "requires_thinking_as_text",
    "requiresReasoningContentOnAssistantMessages": (
        "requires_reasoning_content_on_assistant_messages"
    ),
    "zaiToolStream": "zai_tool_stream",
    "sendSessionAffinityHeaders": "send_session_affinity_headers",
    "sendSessionIdHeader": "send_session_id_header",
    "supportsEagerToolInputStreaming": "supports_eager_tool_input_streaming",
    "supportsLongCacheRetention": "supports_long_cache_retention",
    "requiresOpenAiAnthropicToolPayload": "requires_openai_anthropic_tool_payload",
}


def _normalize_compat(value: Any) -> ModelCatalogCompatConfig | None:
    record = as_optional_record(value)
    if record is None:
        return None
    fields: dict[str, Any] = {}
    for ts_key, py_key in _TS_TO_PY_COMPAT_FIELDS.items():
        if isinstance(record.get(ts_key), bool):
            fields[py_key] = record[ts_key]
    for ts_key, py_key in (
        ("toolSchemaProfile", "tool_schema_profile"),
        ("toolCallArgumentsEncoding", "tool_call_arguments_encoding"),
    ):
        text = normalize_optional_string(record.get(ts_key)) or ""
        if text:
            fields[py_key] = text
    for ts_key, py_key in (
        ("visibleReasoningDetailTypes", "visible_reasoning_detail_types"),
        ("supportedReasoningEfforts", "supported_reasoning_efforts"),
        ("unsupportedToolSchemaKeywords", "unsupported_tool_schema_keywords"),
    ):
        items = normalize_trimmed_string_list(record.get(ts_key))
        if items:
            fields[py_key] = tuple(items)
    effort_map = as_optional_record(record.get("reasoningEffortMap"))
    if effort_map is not None:
        mapped = {
            key.strip(): mapped_value.strip()
            for key, raw_mapped in effort_map.items()
            if key.strip() and isinstance(raw_mapped, str) and (mapped_value := raw_mapped.strip())
        }
        if mapped:
            fields["reasoning_effort_map"] = mapped
    code_mode = normalize_optional_string(record.get("codeMode")) or ""
    if code_mode in ("preferred", "capable"):
        fields["code_mode"] = code_mode
    max_tokens_field = normalize_optional_string(record.get("maxTokensField")) or ""
    if max_tokens_field in ("max_completion_tokens", "max_tokens"):
        fields["max_tokens_field"] = max_tokens_field
    thinking_format = normalize_optional_string(record.get("thinkingFormat")) or ""
    if is_model_catalog_thinking_format(thinking_format):
        fields["thinking_format"] = thinking_format
    if record.get("cacheControlFormat") == "anthropic":
        fields["cache_control_format"] = "anthropic"
    open_router_routing = _normalize_open_router_routing(record.get("openRouterRouting"))
    if open_router_routing is not None:
        fields["open_router_routing"] = open_router_routing
    vercel_routing = _normalize_vercel_gateway_routing(record.get("vercelGatewayRouting"))
    if vercel_routing is not None:
        fields["vercel_gateway_routing"] = vercel_routing
    return ModelCatalogCompatConfig(**fields) if fields else None


def _normalize_status(value: Any) -> ModelCatalogStatus | None:
    status = normalize_optional_string(value) or ""
    return cast(ModelCatalogStatus, status) if status in _MODEL_CATALOG_STATUSES else None


def _normalize_image_token_mode(value: Any) -> str | None:
    mode = normalize_optional_string(value) or ""
    return mode if mode in ("tile", "detail", "provider") else None


def _normalize_media_input(value: Any) -> ModelCatalogMediaInputConfig | None:
    record = as_optional_record(value)
    image = as_optional_record(record.get("image")) if record is not None else None
    if image is None:
        return None
    fields: dict[str, Any] = {}
    for ts_key, py_key in (
        ("maxBytes", "max_bytes"),
        ("maxPixels", "max_pixels"),
        ("maxSidePx", "max_side_px"),
        ("preferredSidePx", "preferred_side_px"),
    ):
        positive = _normalize_positive_integer(image.get(ts_key))
        if positive is not None:
            fields[py_key] = positive
    token_mode = _normalize_image_token_mode(image.get("tokenMode"))
    if token_mode:
        fields["token_mode"] = token_mode
    if not fields:
        return None
    image_config = ModelCatalogImageInputConfig(**fields)
    return ModelCatalogMediaInputConfig(image=image_config)


def normalize_model_catalog_model(value: Any) -> ModelCatalogModel | None:
    """Normalize one raw model entry; ``None`` when the id is missing."""
    record = as_optional_record(value)
    if record is None:
        return None
    model_id = normalize_optional_string(record.get("id")) or ""
    if not model_id:
        return None
    fields: dict[str, Any] = {"id": model_id}
    name = normalize_optional_string(record.get("name")) or ""
    if name:
        fields["name"] = name
    api = _normalize_model_catalog_api(record.get("api"))
    if api is not None:
        fields["api"] = api
    base_url = normalize_optional_string(record.get("baseUrl")) or ""
    if base_url:
        fields["base_url"] = base_url
    headers = _normalize_string_map(record.get("headers"))
    if headers is not None:
        fields["headers"] = headers
    inputs = _normalize_model_catalog_inputs(record.get("input"))
    if inputs is not None:
        fields["input"] = tuple(inputs)
    reasoning = record.get("reasoning")
    if isinstance(reasoning, bool):
        fields["reasoning"] = reasoning
    context_window = as_positive_finite_number(record.get("contextWindow"))
    if context_window is not None:
        fields["context_window"] = float(context_window)
    selection = normalize_model_catalog_context_window_selection(record)
    if selection:
        options = selection.get("contextWindows")
        default = selection.get("contextWindowDefault")
        if isinstance(options, list) and isinstance(default, str):
            fields["context_windows"] = tuple(options)
            fields["context_window_default"] = default
    context_tokens = _normalize_positive_integer(record.get("contextTokens"))
    if context_tokens is not None:
        fields["context_tokens"] = float(context_tokens)
    max_tokens = as_positive_finite_number(record.get("maxTokens"))
    if max_tokens is not None:
        fields["max_tokens"] = float(max_tokens)
    thinking_level_map = _normalize_thinking_level_map(record.get("thinkingLevelMap"))
    if thinking_level_map is not None:
        fields["thinking_level_map"] = thinking_level_map
    cost = _normalize_cost(record.get("cost"))
    if cost is not None:
        fields["cost"] = cost
    compat = _normalize_compat(record.get("compat"))
    if compat is not None:
        fields["compat"] = compat
    media_input = _normalize_media_input(record.get("mediaInput"))
    if media_input is not None:
        fields["media_input"] = media_input
    status = _normalize_status(record.get("status"))
    if status is not None:
        fields["status"] = status
    status_reason = normalize_optional_string(record.get("statusReason")) or ""
    if status_reason:
        fields["status_reason"] = status_reason
    replaces = normalize_trimmed_string_list(record.get("replaces"))
    if replaces:
        fields["replaces"] = tuple(replaces)
    replaced_by = normalize_optional_string(record.get("replacedBy")) or ""
    if replaced_by:
        fields["replaced_by"] = replaced_by
    tags = normalize_trimmed_string_list(record.get("tags"))
    if tags:
        fields["tags"] = tuple(tags)
    return ModelCatalogModel(**fields)


def _normalize_provider(value: Any) -> ModelCatalogProvider | None:
    record = as_optional_record(value)
    if record is None:
        return None
    raw_models = record.get("models")
    models = (
        [model for item in raw_models if (model := normalize_model_catalog_model(item))]
        if isinstance(raw_models, list)
        else []
    )
    if not models:
        return None
    fields: dict[str, Any] = {"models": tuple(models)}
    base_url = normalize_optional_string(record.get("baseUrl")) or ""
    if base_url:
        fields["base_url"] = base_url
    api = _normalize_model_catalog_api(record.get("api"))
    if api is not None:
        fields["api"] = api
    headers = _normalize_string_map(record.get("headers"))
    if headers is not None:
        fields["headers"] = headers
    default_model = normalize_optional_string(record.get("defaultModel")) or ""
    if default_model:
        fields["default_model"] = default_model
    default_utility = normalize_optional_string(record.get("defaultUtilityModel")) or ""
    if default_utility:
        fields["default_utility_model"] = default_utility
    return ModelCatalogProvider(**fields)


def _normalize_providers(
    value: Any, owned: frozenset[str]
) -> dict[str, ModelCatalogProvider] | None:
    record = as_optional_record(value)
    if record is None:
        return None
    providers: dict[str, ModelCatalogProvider] = {}
    for raw_id, raw_provider in record.items():
        provider_id = normalize_provider_id(raw_id)
        if not provider_id or provider_id not in owned:
            continue
        provider = _normalize_provider(raw_provider)
        if provider is not None:
            providers[provider_id] = provider
    return providers or None


def _normalize_aliases(value: Any, owned: frozenset[str]) -> dict[str, ModelCatalogAlias] | None:
    record = as_optional_record(value)
    if record is None:
        return None
    aliases: dict[str, ModelCatalogAlias] = {}
    for raw_alias, raw_target in record.items():
        alias = normalize_provider_id(raw_alias)
        target = as_optional_record(raw_target)
        if not alias or target is None:
            continue
        provider = normalize_provider_id(normalize_optional_string(target.get("provider")) or "")
        if not provider or provider not in owned:
            continue
        fields: dict[str, Any] = {"provider": provider}
        api = _normalize_model_catalog_api(target.get("api"))
        if api is not None:
            fields["api"] = api
        base_url = normalize_optional_string(target.get("baseUrl")) or ""
        if base_url:
            fields["base_url"] = base_url
        aliases[alias] = ModelCatalogAlias(**fields)
    return aliases or None


def _normalize_suppressions(value: Any) -> list[ModelCatalogSuppression] | None:
    if not isinstance(value, list):
        return None
    suppressions: list[ModelCatalogSuppression] = []
    for entry in value:
        record = as_optional_record(entry)
        if record is None:
            continue
        provider = normalize_provider_id(normalize_optional_string(record.get("provider")) or "")
        model = normalize_optional_string(record.get("model")) or ""
        if not provider or not model:
            continue
        fields: dict[str, Any] = {"provider": provider, "model": model}
        reason = normalize_optional_string(record.get("reason")) or ""
        if reason:
            fields["reason"] = reason
        retirement_record = as_optional_record(record.get("retirement"))
        replaced_by = (
            normalize_optional_string(retirement_record.get("replacedBy"))
            if retirement_record is not None
            else None
        )
        retirement = (
            ModelCatalogSuppressionRetirement(replaced_by=replaced_by)
            if retirement_record is not None
            and (retirement_record.get("replacedBy") is None or replaced_by is not None)
            else None
        )
        if retirement is not None:
            fields["retirement"] = retirement
        # Explicit `when: null` counts as present (TS `!== undefined`):
        # with a retirement it drops the rule instead of broadening it.
        when_present = "when" in record
        when_record = as_optional_record(record.get("when"))
        hosts = normalize_trimmed_string_list(
            when_record.get("baseUrlHosts") if when_record is not None else None
        )
        apis = normalize_trimmed_string_list(
            when_record.get("providerConfigApiIn") if when_record is not None else None
        )
        hosts = [host.lower() for host in hosts]
        apis = [api.lower() for api in apis]
        when = (
            ModelCatalogSuppressionWhen(
                base_url_hosts=tuple(hosts), provider_config_api_in=tuple(apis)
            )
            if hosts or apis
            else None
        )
        if when is not None:
            fields["when"] = when
        # A malformed retirement scope must never broaden a persistent model repair.
        if (
            retirement is not None
            and when_present
            and (
                when_record is None
                or when is None
                or (when_record.get("baseUrlHosts") is not None and not hosts)
                or (when_record.get("providerConfigApiIn") is not None and not apis)
            )
        ):
            continue
        suppressions.append(ModelCatalogSuppression(**fields))
    return suppressions or None


def _normalize_discovery(
    value: Any, owned: frozenset[str]
) -> dict[str, ModelCatalogDiscovery] | None:
    record = as_optional_record(value)
    if record is None:
        return None
    discovery: dict[str, ModelCatalogDiscovery] = {}
    for raw_id, raw_mode in record.items():
        provider_id = normalize_provider_id(raw_id)
        mode = normalize_optional_string(raw_mode) or ""
        if provider_id and provider_id in owned and mode in _MODEL_CATALOG_DISCOVERY_MODES:
            discovery[provider_id] = cast(ModelCatalogDiscovery, mode)
    return discovery or None


def normalize_model_catalog(
    value: Any, owned_providers: set[str] | frozenset[str]
) -> ModelCatalog | None:
    """Normalize a raw model catalog for the providers owned by a plugin/manifest."""
    record = as_optional_record(value)
    if record is None:
        return None
    owned = _normalize_owned_provider_set(owned_providers)
    string_map = _normalize_string_map(record.get("modelsDev")) or {}
    models_dev = {
        provider_id: source_id
        for raw_id, source_id in string_map.items()
        if (provider_id := normalize_provider_id(raw_id))
        and provider_id in owned
        and not _is_blocked_object_key(provider_id)
    }
    fields: dict[str, Any] = {}
    if models_dev:
        fields["models_dev"] = models_dev
    providers = _normalize_providers(record.get("providers"), owned)
    if providers is not None:
        fields["providers"] = providers
    aliases = _normalize_aliases(record.get("aliases"), owned)
    if aliases is not None:
        fields["aliases"] = aliases
    suppressions = _normalize_suppressions(record.get("suppressions"))
    if suppressions is not None:
        fields["suppressions"] = tuple(suppressions)
    discovery = _normalize_discovery(record.get("discovery"), owned)
    if discovery is not None:
        fields["discovery"] = discovery
    if record.get("runtimeAugment") is True:
        fields["runtime_augment"] = True
    return ModelCatalog(**fields) if fields else None


def normalize_model_catalog_provider_rows(
    provider: str,
    provider_catalog: ModelCatalogProvider,
    source: ModelCatalogSource,
) -> list[NormalizedModelCatalogRow]:
    """Normalize one provider catalog into sorted runtime rows.

    Provider-level ``api``/``baseUrl``/``headers`` fill row gaps; every
    row carries its ``ref``/``mergeKey`` join identity plus resolved
    ``name``/``input``/``reasoning``/``status`` defaults.
    """
    normalized_provider = normalize_provider_id(provider)
    if not normalized_provider or not isinstance(provider_catalog.models, (list, tuple)):
        return []
    provider_api = _normalize_model_catalog_api(provider_catalog.api)
    provider_base_url = normalize_optional_string(provider_catalog.base_url) or ""
    provider_headers = _normalize_string_map(provider_catalog.headers)
    rows: list[NormalizedModelCatalogRow] = []
    for raw_model in provider_catalog.models:
        # Normalized rows are frozen dataclasses, not plain records, so they
        # bypass re-normalization (TS accepts both shapes because its rows
        # are plain objects; the normalized fields are already valid here).
        model = (
            raw_model
            if isinstance(raw_model, ModelCatalogModel)
            else normalize_model_catalog_model(raw_model)
        )
        if model is None:
            continue
        api = model.api or provider_api
        base_url = model.base_url or provider_base_url
        headers = _merge_string_maps(provider_headers, model.headers or None)
        # Copy through the model snapshot field-by-field so newly added
        # model fields ride along without a hand-maintained list.
        snapshot: dict[str, Any] = {
            field_name: getattr(model, field_name)
            for field_name in ModelCatalogModel.__dataclass_fields__
        }
        # Authoring metadata only: the row type omits `upstreamModel`.
        snapshot.pop("upstream_model", None)
        snapshot.update(
            provider=normalized_provider,
            ref=build_model_catalog_ref(normalized_provider, model.id),
            merge_key=build_model_catalog_merge_key(normalized_provider, model.id),
            name=model.name or model.id,
            source=source,
            input=model.input or _DEFAULT_MODEL_INPUT,
            reasoning=model.reasoning if model.reasoning is not None else False,
            status=model.status or _DEFAULT_MODEL_STATUS,
            api=api,
            base_url=base_url or None,
            headers=headers or {},
        )
        rows.append(NormalizedModelCatalogRow(**snapshot))
    rows.sort(key=lambda row: (row.provider, row.id))
    return rows


__all__ = [
    "normalize_model_catalog",
    "normalize_model_catalog_model",
    "normalize_model_catalog_provider_rows",
]
