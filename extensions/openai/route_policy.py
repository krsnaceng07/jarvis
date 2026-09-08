"""OpenAI provider-owned model route policy (cold artifact, no runtime load).

OpenClaw parity: mirrors ``openclaw-main/extensions/openai/provider-policy-api.ts``
(route core) + ``openclaw-main/extensions/openai/base-url.ts`` (endpoint
classification) + the route-membership subset of
``openclaw-main/extensions/openai/model-route-contract.ts``.

Ownership: this module is provider-owned policy. Core consumes it through
``src/agents/openai_model_routes.py`` (mirroring OpenClaw's
``createProviderModelRoutesResolver`` cold-artifact path), never the
reverse. Stdlib only; pure dicts in/out so the runtime-selection hot path
never loads provider runtime.

Not ported here (separate surfaces):
- ``normalizeModelCatalogId`` / ``projectConfiguredModelRow`` (catalog
  projection, not route selection).
- ``resolveThinkingProfile`` (thinking-policy surface).
- Reasoning-effort tables in ``model-route-contract.ts`` (turn payload,
  not route selection).
- The generic ``resolveMergedModelProviderModels`` /
  ``createModelProviderRouteOverrideResolver`` config helpers
  (``src/config/model-provider-config.ts``) are inlined below as private
  helpers. If a second provider needs them, extract one shared helper
  and migrate both call sites in the same change.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

#: Official OpenAI Platform endpoint. Mirrors ``OPENAI_API_BASE_URL``.
OPENAI_API_BASE_URL = "https://api.openai.com/v1"
#: Official ChatGPT Codex endpoint. Mirrors ``OPENAI_CODEX_RESPONSES_BASE_URL``.
OPENAI_CODEX_RESPONSES_BASE_URL = "https://chatgpt.com/backend-api/codex"

OPENAI_RESPONSES_API = "openai-responses"
OPENAI_COMPLETIONS_API = "openai-completions"
OPENAI_CHATGPT_RESPONSES_API = "openai-chatgpt-responses"
OPENAI_PROVIDER_ID = "openai"
OPENAI_AGENT_RUNTIME_ID = "openclaw"
CODEX_AGENT_RUNTIME_ID = "codex"

_OPENAI_PLATFORM_PATHS = frozenset({"/", "/v1", "/v1/"})
_OPENAI_CHATGPT_PATHS = frozenset(
    {
        "/backend-api",
        "/backend-api/",
        "/backend-api/v1",
        "/backend-api/v1/",
        "/backend-api/codex",
        "/backend-api/codex/",
        "/backend-api/codex/v1",
        "/backend-api/codex/v1/",
        "/backend-api/codex/responses",
        "/backend-api/codex/responses/",
    }
)

#: Models with known first-party Platform and ChatGPT transports.
_OPENAI_DUAL_ROUTE_MODEL_IDS = frozenset(
    {
        "gpt-6-astra",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.5",
        "gpt-5.5-pro",
        "gpt-5.4",
        "gpt-5.4-pro",
        "gpt-5.4-mini",
    }
)
#: Direct aliases excluded from the ChatGPT catalog.
_OPENAI_PLATFORM_ONLY_ROUTE_MODEL_IDS = frozenset({"chat-latest", "gpt-5.6"})
_OPENAI_SUBSCRIPTION_ONLY_ROUTE_MODEL_IDS = frozenset({"gpt-5.3-codex-spark"})
_LEGACY_CODEX_MODEL_ALIAS = "gpt-5.4-codex"

_REASONING_EFFORT_RE = re.compile(r"^(minimal|low|medium|high|xhigh|max|ultra)$")


def _normalize_provider_id(provider: Any) -> str:
    return provider.strip().lower() if isinstance(provider, str) else ""


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


# ---------------------------------------------------------------------------
# Endpoint classification (base-url.ts)
# ---------------------------------------------------------------------------


def classify_openai_base_url(base_url: Any) -> str:
    """Classify an endpoint: unresolved|platform|chatgpt|custom|invalid.

    Mirrors ``classifyOpenAIBaseUrl``. Official remote endpoints never
    reinterpret their plaintext (http) form as an eligible native route.
    """
    if base_url is None or base_url == "":
        return "unresolved"
    if not isinstance(base_url, str):
        return "invalid"
    trimmed = base_url.strip()
    if not trimmed:
        return "unresolved"
    try:
        url = urlparse(trimmed)
    except Exception:
        return "invalid"
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
        return "invalid"
    host = url.hostname.lower().rstrip(".")
    if host in ("api.openai.com", "chatgpt.com"):
        if url.scheme != "https" or url.port or url.query or url.fragment:
            return "invalid"
        path = url.path or "/"
        if host == "api.openai.com" and path in _OPENAI_PLATFORM_PATHS:
            return "platform"
        if host == "chatgpt.com" and path in _OPENAI_CHATGPT_PATHS:
            return "chatgpt"
        return "invalid"
    return "custom"


def is_openai_codex_base_url(base_url: Any) -> bool:
    """Mirror ``isOpenAICodexBaseUrl``."""
    return classify_openai_base_url(base_url) == "chatgpt"


# ---------------------------------------------------------------------------
# Model route membership (model-route-contract.ts subset)
# ---------------------------------------------------------------------------


def normalize_openai_model_route_id(value: Any) -> str:
    """Collapse only the shipped legacy alias; custom ids keep identity.

    Mirrors ``normalizeOpenAIModelRouteId`` (model ids are case-sensitive).
    """
    model_id = value.strip() if isinstance(value, str) else ""
    lowered = model_id.lower()
    if lowered == _LEGACY_CODEX_MODEL_ALIAS or lowered == f"openai/{_LEGACY_CODEX_MODEL_ALIAS}":
        return "gpt-5.4"
    return model_id


def _membership_id(value: Any) -> str:
    return normalize_openai_model_route_id(value).lower()


def is_openai_dual_route_model_id(value: Any) -> bool:
    """Mirror ``isOpenAIDualRouteModelId``."""
    return _membership_id(value) in _OPENAI_DUAL_ROUTE_MODEL_IDS


def is_openai_platform_only_route_model_id(value: Any) -> bool:
    """Mirror ``isOpenAIPlatformOnlyRouteModelId``."""
    return _membership_id(value) in _OPENAI_PLATFORM_ONLY_ROUTE_MODEL_IDS


def is_openai_subscription_only_route_model_id(value: Any) -> bool:
    """Mirror ``isOpenAISubscriptionOnlyRouteModelId``."""
    return _membership_id(value) in _OPENAI_SUBSCRIPTION_ONLY_ROUTE_MODEL_IDS


# ---------------------------------------------------------------------------
# Authored-config readers (resolveAuthoredOpenAIProviderConfig + merged models)
# ---------------------------------------------------------------------------


def resolve_authored_openai_provider_config(params: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve authored OpenAI provider config without activating runtime.

    Mirrors ``resolveAuthoredOpenAIProviderConfig``: exact-key precedence,
    then case-insensitive fallback; duplicate keys merge (later fields win,
    omitted model rows keep the earlier catalog).
    """
    provider = params.get("provider")
    cfg = params.get("config")
    if not isinstance(provider, str) or _normalize_provider_id(provider) != OPENAI_PROVIDER_ID:
        return None
    providers = cfg.get("models", {}).get("providers") if isinstance(cfg, dict) else None
    if not isinstance(providers, dict):
        return None
    requested = provider.strip()
    exact_key = next((k for k in providers if isinstance(k, str) and k.strip() == requested), None)
    fallback_key = next(
        (
            k
            for k in providers
            if isinstance(k, str) and _normalize_provider_id(k) == OPENAI_PROVIDER_ID
        ),
        None,
    )
    provider_key = (exact_key or fallback_key or "").strip()
    if not provider_key:
        return None
    matched: dict[str, Any] | None = None
    for provider_id, candidate in providers.items():
        if not (isinstance(provider_id, str) and provider_id.strip() == provider_key):
            continue
        if not isinstance(candidate, dict):
            continue
        matched = (
            {**matched, **candidate, "models": candidate.get("models", matched.get("models"))}
            if matched is not None
            else candidate
        )
    return matched


def _normalize_model_id(provider: str, model_id: str) -> str:
    """Strip a same-provider prefix. Mirrors the local ``normalizeModelId``."""
    trimmed = model_id.strip()
    slash = trimmed.find("/")
    if slash > 0 and _normalize_provider_id(trimmed[:slash]) == _normalize_provider_id(provider):
        return trimmed[slash + 1 :].strip()
    return trimmed


def _resolve_merged_model_provider_models(
    models: Any, normalize_model_id: Any
) -> dict[str, dict[str, Any]]:
    """Index configured model rows; earlier rows stay authoritative.

    Mirrors ``resolveMergedModelProviderModels``: later duplicates only
    supply top-level fields the first row omitted.
    """
    merged: dict[str, dict[str, Any]] = {}
    for model in models if isinstance(models, list) else []:
        if not isinstance(model, dict):
            continue
        model_id = normalize_model_id(model.get("id"))
        if not model_id:
            continue
        existing = merged.get(model_id)
        merged[model_id] = {**model, **existing} if existing is not None else model
    return merged


def _has_non_empty_record(value: Any) -> bool:
    return isinstance(value, dict) and len(value) > 0


def _has_request_compat_overrides(compat: Any) -> bool:
    """Mirror ``hasRequestCompatOverrides``."""
    if not isinstance(compat, dict):
        return False
    for key, value in compat.items():
        if key == "supportsReasoningEffort":
            if value is not True:
                return True
            continue
        if key == "supportedReasoningEfforts":
            if not (
                isinstance(value, list)
                and len(value) > 0
                and all(
                    isinstance(effort, str) and _REASONING_EFFORT_RE.match(effort)
                    for effort in value
                )
            ):
                return True
            continue
        return True
    return False


def _create_route_override_resolver(
    provider_config: dict[str, Any] | None, canonicalize_model_id: Any
) -> Any:
    """Return a ``modelId -> present|none`` override resolver.

    Mirrors ``createModelProviderRouteOverrideResolver``.
    """
    if provider_config is None:
        return lambda model_id=None: "none"
    if (
        isinstance(provider_config.get("localService"), dict)
        or _has_non_empty_record(provider_config.get("headers"))
        or _has_non_empty_record(provider_config.get("request"))
        or _has_non_empty_record(provider_config.get("params"))
        or isinstance(provider_config.get("authHeader"), bool)
        or isinstance(provider_config.get("timeoutSeconds"), (int, float))
    ):
        return lambda model_id=None: "present"

    def _canonicalize(model_id: str) -> str:
        # Mirrors model-provider-config.ts: strip a same-provider prefix
        # first, then apply the surface canonicalization. (Route-table keys
        # in create_model_routes_resolver intentionally do NOT strip; only
        # the override lookup composes this way, so provider-qualified and
        # bare ids stay distinct routes but share override facts.)
        normalized = _normalize_model_id(OPENAI_PROVIDER_ID, model_id)
        canonical = canonicalize_model_id(normalized)
        canonical = canonical.strip() if isinstance(canonical, str) else ""
        return canonical or normalized

    merged: dict[str, dict[str, Any]] | None = None

    def _resolve(model_id: Any = None) -> str:
        nonlocal merged
        if not model_id:
            return "none"
        canonical_id = _canonicalize(model_id)
        if merged is None:
            merged = _resolve_merged_model_provider_models(
                provider_config.get("models"), _canonicalize
            )
        configured = merged.get(canonical_id)
        if configured is not None and (
            _has_non_empty_record(configured.get("headers"))
            or _has_non_empty_record(configured.get("params"))
            or _has_request_compat_overrides(configured.get("compat"))
        ):
            return "present"
        return "none"

    return _resolve


# ---------------------------------------------------------------------------
# Route resolution (provider-policy-api.ts route core)
# ---------------------------------------------------------------------------


def _first_route_base_url(*values: Any) -> Any:
    for value in values:
        if isinstance(value, str):
            if value.strip():
                return value.strip()
            continue
        if value is not None:
            return value
    return None


def _concrete_base_url(value: Any, fallback: str) -> str:
    return _optional_str(value) or fallback


def _resolve_environment_base_url(env: Any) -> str | None:
    if isinstance(env, dict):
        return _optional_str(env.get("OPENAI_BASE_URL"))
    return None


def _is_http_base_url(base_url: Any) -> bool:
    if not isinstance(base_url, str):
        return False
    try:
        from urllib.parse import urlparse as _urlparse

        return _urlparse(base_url.strip()).scheme == "http"
    except Exception:
        return False


def _codex_can_reproduce_route(candidate: dict[str, Any], source_base_url: Any = None) -> bool:
    """Mirror ``codexCanReproduceRoute``.

    Only an exact official HTTPS Responses/ChatGPT route with no authored
    provider request override may select Codex implicitly. The source
    protocol is retained so normalization cannot silently launder an
    unreproducible route into Codex-compatible.
    """
    source = source_base_url if source_base_url is not None else candidate.get("baseUrl")
    if _is_http_base_url(source) or candidate.get("requestTransportOverrides") == "present":
        return False
    endpoint_kind = classify_openai_base_url(candidate.get("baseUrl"))
    return (candidate.get("api") == OPENAI_RESPONSES_API and endpoint_kind == "platform") or (
        candidate.get("api") == OPENAI_CHATGPT_RESPONSES_API and endpoint_kind == "chatgpt"
    )


def _with_runtime_policy(candidate: dict[str, Any], source_base_url: Any = None) -> dict[str, Any]:
    compatible = (
        (OPENAI_AGENT_RUNTIME_ID, CODEX_AGENT_RUNTIME_ID)
        if _codex_can_reproduce_route(candidate, source_base_url)
        else (OPENAI_AGENT_RUNTIME_ID,)
    )
    return {**candidate, "runtimePolicy": {"compatibleIds": list(compatible)}}


def _default_runtime_id_for_route(candidate: dict[str, Any], source_base_url: Any = None) -> str:
    return (
        CODEX_AGENT_RUNTIME_ID
        if _codex_can_reproduce_route(candidate, source_base_url)
        else OPENAI_AGENT_RUNTIME_ID
    )


def _route(candidate: dict[str, Any], source_base_url: Any = None) -> dict[str, Any]:
    compatible = _with_runtime_policy(candidate, source_base_url)
    return {
        "kind": "routes",
        "routes": [compatible],
        "defaultRuntimeId": _default_runtime_id_for_route(compatible, source_base_url),
    }


def _resolve_single_observed_model_route(
    context: dict[str, Any], observed: Any = None
) -> dict[str, Any]:
    if _normalize_provider_id(context.get("provider")) != OPENAI_PROVIDER_ID:
        return {
            "kind": "incompatible",
            "code": "openai-route-provider-mismatch",
            "message": f"OpenAI route policy cannot resolve provider {context.get('provider') or '(empty)'}.",
        }
    observed = observed or {}
    model_api = _optional_str((context.get("configuredModel") or {}).get("api"))
    request_overrides = context.get("requestTransportOverrides") or "none"
    provider_api = _optional_str((context.get("configuredProvider") or {}).get("api"))
    model_base = _first_route_base_url((context.get("configuredModel") or {}).get("baseUrl"))
    provider_base = _first_route_base_url((context.get("configuredProvider") or {}).get("baseUrl"))
    env_base = _first_route_base_url(_resolve_environment_base_url(context.get("env")))
    observed_api = _optional_str(observed.get("api"))
    observed_base = _first_route_base_url(observed.get("baseUrl"))
    has_observed = observed_api is not None or observed_base is not None

    effective_api: str | None = None
    effective_base: Any = None
    configured_route = False
    custom_default_api = OPENAI_COMPLETIONS_API

    # Model facts override provider facts field-by-field, which override the
    # environment. Observed rows are atomic fallback only.
    if model_api is not None or model_base is not None:
        configured_route = True
        effective_api = model_api if model_api is not None else provider_api
        effective_base = model_base
        if model_base is None:
            lower_base = provider_base if provider_base is not None else env_base
            lower_kind = classify_openai_base_url(lower_base)
            effective_base = lower_base if lower_kind in ("custom", "invalid") else None
    elif provider_api is not None or provider_base is not None:
        configured_route = True
        effective_api = provider_api
        effective_base = provider_base
        if provider_base is None:
            env_kind = classify_openai_base_url(env_base)
            if env_kind in ("custom", "invalid"):
                effective_base = env_base
    elif env_base is not None:
        configured_route = True
        effective_base = env_base
        custom_default_api = OPENAI_RESPONSES_API
    else:
        effective_api = observed_api
        effective_base = observed_base

    endpoint_kind = classify_openai_base_url(effective_base)
    if endpoint_kind == "invalid":
        return {
            "kind": "incompatible",
            "code": "invalid-openai-base-url",
            "message": "OpenAI model route baseUrl must be a non-empty URL string.",
        }
    chatgpt_api = (effective_api or "").lower() == OPENAI_CHATGPT_RESPONSES_API
    authored_chatgpt_api = (model_api or "").lower() == OPENAI_CHATGPT_RESPONSES_API or (
        provider_api or ""
    ).lower() == OPENAI_CHATGPT_RESPONSES_API

    if endpoint_kind == "custom":
        if chatgpt_api and not authored_chatgpt_api:
            return {
                "kind": "incompatible",
                "code": "custom-chatgpt-relay-requires-configuration",
                "message": "Custom ChatGPT relays require an explicitly configured ChatGPT adapter.",
            }
        observed_platform_api = (
            observed_api if observed_api in (OPENAI_RESPONSES_API, OPENAI_COMPLETIONS_API) else None
        )
        custom_api = effective_api or observed_platform_api or custom_default_api
        if custom_api not in (
            OPENAI_RESPONSES_API,
            OPENAI_COMPLETIONS_API,
            OPENAI_CHATGPT_RESPONSES_API,
        ):
            return {
                "kind": "incompatible",
                "code": "unsupported-custom-openai-api",
                "message": f"{custom_api} is not an OpenAI-compatible model adapter.",
            }
        return _route(
            {
                "api": custom_api,
                "baseUrl": _concrete_base_url(effective_base, OPENAI_API_BASE_URL),
                "authRequirement": "subscription"
                if custom_api.lower() == OPENAI_CHATGPT_RESPONSES_API
                else "api-key",
                "requestTransportOverrides": request_overrides,
            },
            effective_base,
        )

    if (endpoint_kind == "platform" and chatgpt_api) or (
        endpoint_kind == "chatgpt" and effective_api is not None and not chatgpt_api
    ):
        return {
            "kind": "incompatible",
            "code": "conflicting-official-openai-route",
            "message": "OpenAI model API and baseUrl select different official transports.",
        }
    if effective_api is not None and effective_api not in (
        OPENAI_RESPONSES_API,
        OPENAI_COMPLETIONS_API,
        OPENAI_CHATGPT_RESPONSES_API,
    ):
        return {
            "kind": "incompatible",
            "code": "unsupported-official-openai-api",
            "message": f"{effective_api} is not an OpenAI Platform model adapter.",
        }

    model_id = normalize_openai_model_route_id(context.get("modelId"))
    source_base = effective_base
    # An authored Completions adapter is a concrete transport contract, not an
    # alias for Responses; the OpenClaw runtime owns that request.
    platform_api = (
        OPENAI_COMPLETIONS_API
        if configured_route and effective_api == OPENAI_COMPLETIONS_API
        else OPENAI_RESPONSES_API
    )
    platform_route = _with_runtime_policy(
        {
            "api": platform_api,
            "baseUrl": _concrete_base_url(source_base, OPENAI_API_BASE_URL)
            if classify_openai_base_url(source_base) == "platform"
            and _is_http_base_url(source_base)
            else OPENAI_API_BASE_URL,
            "authRequirement": "api-key",
            "requestTransportOverrides": request_overrides,
        },
        source_base,
    )
    chatgpt_route = _with_runtime_policy(
        {
            "api": OPENAI_CHATGPT_RESPONSES_API,
            "baseUrl": OPENAI_CODEX_RESPONSES_BASE_URL,
            "authRequirement": "subscription",
            "requestTransportOverrides": request_overrides,
        },
        source_base,
    )
    platform_only = is_openai_platform_only_route_model_id(model_id)
    subscription_only = is_openai_subscription_only_route_model_id(model_id)
    dual_route = is_openai_dual_route_model_id(model_id)

    # Observed catalog transport is not authored route intent. Known model
    # contracts stay stable regardless of which sibling row was seen.
    if not configured_route:
        if subscription_only:
            return _route(chatgpt_route, source_base)
        if platform_only:
            return _route(platform_route, source_base)
        if dual_route:
            return {
                "kind": "routes",
                "defaultRuntimeId": _default_runtime_id_for_route(platform_route, source_base),
                "routes": [platform_route, chatgpt_route],
            }

    if endpoint_kind == "chatgpt" or chatgpt_api:
        if platform_only:
            return {
                "kind": "incompatible",
                "code": "platform-only-model-on-chatgpt",
                "message": f"{model_id} is available only through OpenAI Platform API-key authentication.",
            }
        return _route(chatgpt_route, source_base)

    if subscription_only:
        return {
            "kind": "incompatible",
            "code": "subscription-only-model-on-platform",
            "message": f"{model_id} is available only through ChatGPT subscription authentication.",
        }

    if not configured_route and not has_observed:
        return {
            "kind": "indeterminate",
            "defaultRuntimeId": OPENAI_AGENT_RUNTIME_ID
            if request_overrides == "present"
            else CODEX_AGENT_RUNTIME_ID,
        }
    return _route(platform_route, source_base)


def _has_authored_route_facts(context: dict[str, Any]) -> bool:
    return (
        _optional_str((context.get("configuredModel") or {}).get("api")) is not None
        or _first_route_base_url((context.get("configuredModel") or {}).get("baseUrl")) is not None
        or _optional_str((context.get("configuredProvider") or {}).get("api")) is not None
        or _first_route_base_url((context.get("configuredProvider") or {}).get("baseUrl"))
        is not None
        or _first_route_base_url(_resolve_environment_base_url(context.get("env"))) is not None
    )


def _authored_route_needs_observed_platform_api(context: dict[str, Any]) -> bool:
    if (
        _optional_str((context.get("configuredModel") or {}).get("api")) is not None
        or _optional_str((context.get("configuredProvider") or {}).get("api")) is not None
    ):
        return False
    authored_base = _first_route_base_url(
        (context.get("configuredModel") or {}).get("baseUrl"),
        (context.get("configuredProvider") or {}).get("baseUrl"),
        _resolve_environment_base_url(context.get("env")),
    )
    return classify_openai_base_url(authored_base) == "custom"


def _canonical_route_candidate_base_url(base_url: str) -> str:
    try:
        from urllib.parse import urlparse as _parse, urlunparse as _unparse

        parts = _parse(base_url)
        path = parts.path.rstrip("/") or "/"
        return _unparse(
            (parts.scheme, parts.netloc, path, parts.params, parts.query, parts.fragment)
        )
    except Exception:
        return base_url


def _route_candidate_key(candidate: dict[str, Any]) -> str:
    return "\u0000".join(
        [
            str(candidate.get("api")),
            _canonical_route_candidate_base_url(str(candidate.get("baseUrl"))),
            str(candidate.get("authRequirement")),
            str(candidate.get("requestTransportOverrides")),
            *[str(rid) for rid in (candidate.get("runtimePolicy") or {}).get("compatibleIds", [])],
        ]
    )


def _compare_route_candidates(a: dict[str, Any], b: dict[str, Any]) -> int:
    def _auth_order(candidate: dict[str, Any]) -> int:
        return 0 if candidate.get("authRequirement") == "api-key" else 1

    if _auth_order(a) != _auth_order(b):
        return _auth_order(a) - _auth_order(b)
    if a.get("api") != b.get("api"):
        return -1 if str(a.get("api")) < str(b.get("api")) else 1
    if a.get("baseUrl") != b.get("baseUrl"):
        return -1 if str(a.get("baseUrl")) < str(b.get("baseUrl")) else 1
    return 0


def _ambiguous_group(message: str) -> dict[str, Any]:
    return {"kind": "incompatible", "code": "ambiguous-openai-route-group", "message": message}


def _resolve_authored_observed_fallback(observed_routes: list[dict[str, Any]]) -> dict[str, Any]:
    platform_apis: set[str] = set()
    for observed in observed_routes:
        api = _optional_str(observed.get("api"))
        if not api or api == OPENAI_CHATGPT_RESPONSES_API:
            continue
        if api not in (OPENAI_RESPONSES_API, OPENAI_COMPLETIONS_API):
            return {
                "kind": "incompatible",
                "resolution": {
                    "kind": "incompatible",
                    "code": "unsupported-custom-openai-api",
                    "message": f"{api} is not an OpenAI-compatible model adapter.",
                },
            }
        platform_apis.add(api)
    if len(platform_apis) > 1:
        return {
            "kind": "incompatible",
            "resolution": _ambiguous_group(
                "Observed OpenAI routes disagree on the Platform adapter for an authored endpoint."
            ),
        }
    api = next(iter(platform_apis), None)
    return {"kind": "observed", **({"route": {"api": api}} if api else {})}


def resolve_model_routes(context: dict[str, Any]) -> dict[str, Any]:
    """Resolve every physical row for one logical OpenAI model, in provider order.

    Mirrors ``resolveModelRoutes`` (provider-policy-api.ts). Returns one of:
    ``routes`` (with ``defaultRuntimeId``), ``incompatible`` (with
    ``code``/``message``), or ``indeterminate`` (unknown model, no facts).
    """
    observed_routes = [
        observed
        for observed in (context.get("observedRoutes") or [])
        if isinstance(observed, dict)
        and (observed.get("api") is not None or observed.get("baseUrl") is not None)
    ]
    if _has_authored_route_facts(context):
        if _authored_route_needs_observed_platform_api(context):
            fallback = _resolve_authored_observed_fallback(observed_routes)
            if fallback.get("kind") == "incompatible":
                return fallback["resolution"]
            return _resolve_single_observed_model_route(context, fallback.get("route"))
        return _resolve_single_observed_model_route(context)
    if len(observed_routes) <= 1:
        return _resolve_single_observed_model_route(
            context, observed_routes[0] if observed_routes else None
        )

    resolutions = [
        _resolve_single_observed_model_route(context, observed) for observed in observed_routes
    ]
    incompatibles = sorted(
        (r for r in resolutions if r.get("kind") == "incompatible"),
        key=lambda r: (r.get("code", ""), r.get("message", "")),
    )
    if incompatibles:
        return incompatibles[0]

    routes_by_key: dict[str, dict[str, Any]] = {}
    for resolution in resolutions:
        if resolution.get("kind") != "routes":
            continue
        for candidate in resolution.get("routes", []):
            key = _route_candidate_key(candidate)
            existing = routes_by_key.get(key)
            if existing is None or str(candidate.get("baseUrl")) < str(existing.get("baseUrl")):
                routes_by_key[key] = candidate
    from functools import cmp_to_key

    routes = sorted(routes_by_key.values(), key=cmp_to_key(_compare_route_candidates))
    auth_requirements = {route.get("authRequirement") for route in routes}
    if len(routes) > len(auth_requirements):
        return _ambiguous_group(
            "Observed OpenAI routes contain multiple endpoints for the same authentication class."
        )
    if not routes:
        return _resolve_single_observed_model_route(context)
    return {
        "kind": "routes",
        "routes": routes,
        "defaultRuntimeId": OPENAI_AGENT_RUNTIME_ID
        if any(
            r.get("kind") == "routes" and r.get("defaultRuntimeId") == OPENAI_AGENT_RUNTIME_ID
            for r in resolutions
        )
        else _default_runtime_id_for_route(routes[0]),
    }


def create_model_routes_resolver(params: dict[str, Any]) -> Any:
    """Build a reusable resolver over one stable authored config view.

    Mirrors ``createProviderModelRoutesResolver`` for the OpenAI provider:
    merges provider config once, precomputes override presence, then
    resolves each observed model row against it.
    """
    provider = _normalize_provider_id(params.get("provider"))
    if provider != OPENAI_PROVIDER_ID:
        return lambda observed=None: None
    cfg = params.get("config")
    env = params.get("env")
    provider_config = resolve_authored_openai_provider_config(
        {"provider": OPENAI_PROVIDER_ID, "config": cfg}
    )
    configured_provider = (
        {"api": provider_config.get("api"), "baseUrl": provider_config.get("baseUrl")}
        if isinstance(provider_config, dict)
        else None
    )
    # Route-table keys use the surface canonicalization only (legacy-alias
    # collapse); a provider-qualified id stays distinct from the bare id.
    # Mirrors the canonicalizeModelId in provider-model-routes.ts.
    canonicalize = lambda model_id: normalize_openai_model_route_id(model_id)  # noqa: E731

    def _merged_models() -> dict[str, dict[str, Any]]:
        return _resolve_merged_model_provider_models(
            provider_config.get("models") if isinstance(provider_config, dict) else None,
            canonicalize,
        )

    merged_models = _merged_models()
    override_resolver = _create_route_override_resolver(provider_config, canonicalize)
    if params.get("requestTransportOverrides") == "present":
        presence: Any = lambda model_id=None: "present"  # noqa: E731
    else:
        presence = override_resolver
    per_model_presence = {model_id: presence(model_id) for model_id in merged_models}

    def _resolve(observed: dict[str, Any] | None = None) -> dict[str, Any] | None:
        observed = observed or {}
        raw_model_id = observed.get("modelId")
        model_id = canonicalize(raw_model_id) if isinstance(raw_model_id, str) else None
        configured_model_row = merged_models.get(model_id) if model_id else None
        # Mirror projectConfiguredModelRoute: only present fields project.
        configured_model = None
        if isinstance(configured_model_row, dict):
            projected = {
                key: configured_model_row[key]
                for key in ("api", "baseUrl")
                if configured_model_row.get(key) is not None
            }
            configured_model = projected or None
        transport_overrides = (
            per_model_presence.get(model_id, presence()) if model_id else presence()
        )
        observed_rows = observed.get("observedRoutes")
        return resolve_model_routes(
            {
                "provider": OPENAI_PROVIDER_ID,
                **({"modelId": model_id} if model_id else {}),
                "requestTransportOverrides": transport_overrides,
                **({"configuredModel": configured_model} if configured_model else {}),
                **({"configuredProvider": configured_provider} if configured_provider else {}),
                "env": env,
                **({"observedRoutes": observed_rows} if observed_rows else {}),
            }
        )

    return _resolve


__all__ = [
    "CODEX_AGENT_RUNTIME_ID",
    "OPENAI_AGENT_RUNTIME_ID",
    "OPENAI_API_BASE_URL",
    "OPENAI_CHATGPT_RESPONSES_API",
    "OPENAI_CODEX_RESPONSES_BASE_URL",
    "OPENAI_COMPLETIONS_API",
    "OPENAI_PROVIDER_ID",
    "OPENAI_RESPONSES_API",
    "classify_openai_base_url",
    "create_model_routes_resolver",
    "is_openai_codex_base_url",
    "is_openai_dual_route_model_id",
    "is_openai_platform_only_route_model_id",
    "is_openai_subscription_only_route_model_id",
    "normalize_openai_model_route_id",
    "resolve_authored_openai_provider_config",
    "resolve_model_routes",
]
