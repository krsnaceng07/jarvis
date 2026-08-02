"""jarvis.agents.embedded_agent_runner.model_inline_provider — inline provider config conversion.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/model.inline-provider.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`InlineProviderConfig` — the inline provider config shape.
- :data:`SUPPORTED_TRANSPORT_APIS` — the set of supported
  transport API ids.
- :func:`normalize_resolved_transport_api` — return a supported
  transport API id from raw config, or ``None`` for unsupported
  values.
- :func:`sanitize_model_headers` — clean configured model
  headers, optionally stripping secret-ref markers.
- :func:`resolve_provider_model_input` — resolve the model input
  modalities with Foundry legacy vision-model compatibility.
- :func:`build_inline_provider_models` — build runtime model
  records from inline provider config.

Phase 7.3c — focused minimal port.

The OpenClaw source is tightly coupled to the provider request
config and local-service attach layers. The Python port keeps the
public surface but delegates the heavy request-config and
local-service attach steps to installable hooks so the host can
plug in the real provider-request-config layer as it lands.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set


#: Supported transport API ids. Mirrors the ``switch`` cases in
#: :func:`normalizeResolvedTransportApi``
#: (``model.inline-provider.ts:42-60``).
SUPPORTED_TRANSPORT_APIS: Set[str] = {
    "anthropic-messages",
    "bedrock-converse-stream",
    "github-copilot",
    "google-generative-ai",
    "google-vertex",
    "ollama",
    "openai-chatgpt-responses",
    "openai-completions",
    "openai-responses",
    "azure-openai-responses",
}


#: Inline provider config shape. Mirrors
#: :class:`InlineProviderConfig``
#: (``model.inline-provider.ts:26-39``).
InlineProviderConfig = Dict[str, Any]


#: Inline model entry shape. Mirrors ``InlineModelEntry``
#: (``model.inline-provider.ts:19-24``).
InlineModelEntry = Dict[str, Any]


#: Secret-ref header value marker check. The OpenClaw source uses
#: :func:`isSecretRefHeaderValueMarker` from
#: ``model-auth-markers.js``. The Python port delegates to an
#: installable hook that defaults to ``False``.
_IS_SECRET_REF_HEADER_VALUE_MARKER: Callable[[str], bool] = lambda _value: False


def set_is_secret_ref_header_value_marker_hook(
    hook: Callable[[str], bool],
) -> None:
    """Install a custom secret-ref header marker check hook."""
    global _IS_SECRET_REF_HEADER_VALUE_MARKER
    _IS_SECRET_REF_HEADER_VALUE_MARKER = hook


#: Google API base URL normalizer. The OpenClaw source uses
#: :func:`normalizeGoogleApiBaseUrl` from
#: ``infra/google-api-base-url.js``. The Python port delegates to
#: an installable hook.
_NORMALIZE_GOOGLE_API_BASE_URL: Callable[[Optional[str]], Optional[str]] = (
    lambda value: value
)


def set_normalize_google_api_base_url_hook(
    hook: Callable[[Optional[str]], Optional[str]],
) -> None:
    """Install a custom Google API base URL normalizer hook."""
    global _NORMALIZE_GOOGLE_API_BASE_URL
    _NORMALIZE_GOOGLE_API_BASE_URL = hook


#: Provider request config resolver. The host installs the real
#: :func:`resolveProviderRequestConfig`` when the provider-request
#: config layer lands. The default returns a passthrough dict.
_RESOLVE_PROVIDER_REQUEST_CONFIG: Callable[..., Dict[str, Any]] = (
    lambda **kwargs: {
        "api": kwargs.get("api"),
        "baseUrl": kwargs.get("baseUrl"),
        "headers": kwargs.get("headers") or {},
    }
)


def set_resolve_provider_request_config_hook(
    hook: Callable[..., Dict[str, Any]],
) -> None:
    """Install a custom provider request config resolver hook."""
    global _RESOLVE_PROVIDER_REQUEST_CONFIG
    _RESOLVE_PROVIDER_REQUEST_CONFIG = hook


#: Provider request sanitizer. The host installs the real
#: :func:`sanitizeConfiguredModelProviderRequest`` when the
#: provider-request config layer lands. The default returns the
#: input unchanged.
_SANITIZE_CONFIGURED_MODEL_PROVIDER_REQUEST: Callable[[Any], Any] = (
    lambda value: value
)


def set_sanitize_configured_model_provider_request_hook(
    hook: Callable[[Any], Any],
) -> None:
    """Install a custom configured-request sanitizer hook."""
    global _SANITIZE_CONFIGURED_MODEL_PROVIDER_REQUEST
    _SANITIZE_CONFIGURED_MODEL_PROVIDER_REQUEST = hook


#: Provider request transport attacher. The host installs the
#: real :func:`attachModelProviderRequestTransport`` when the
#: provider-request transport layer lands. The default returns
#: the model unchanged.
_ATTACH_MODEL_PROVIDER_REQUEST_TRANSPORT: Callable[[Dict[str, Any], Any], Dict[str, Any]] = (
    lambda model, _request: model
)


def set_attach_model_provider_request_transport_hook(
    hook: Callable[[Dict[str, Any], Any], Dict[str, Any]],
) -> None:
    """Install a custom attach-model-provider-request-transport hook."""
    global _ATTACH_MODEL_PROVIDER_REQUEST_TRANSPORT
    _ATTACH_MODEL_PROVIDER_REQUEST_TRANSPORT = hook


#: Provider local-service attacher. The host installs the real
#: :func:`attachModelProviderLocalService`` when the
#: provider-local-service layer lands. The default returns the
#: model unchanged.
_ATTACH_MODEL_PROVIDER_LOCAL_SERVICE: Callable[[Dict[str, Any], Any], Dict[str, Any]] = (
    lambda model, _local_service: model
)


def set_attach_model_provider_local_service_hook(
    hook: Callable[[Dict[str, Any], Any], Dict[str, Any]],
) -> None:
    """Install a custom attach-model-provider-local-service hook."""
    global _ATTACH_MODEL_PROVIDER_LOCAL_SERVICE
    _ATTACH_MODEL_PROVIDER_LOCAL_SERVICE = hook


def normalize_resolved_transport_api(
    api: Any,
) -> Optional[str]:
    """Return a supported transport API id, or ``None``.

    Mirrors :func:`normalizeResolvedTransportApi``
    (``model.inline-provider.ts:42-60``).
    """
    if isinstance(api, str) and api in SUPPORTED_TRANSPORT_APIS:
        return api
    return None


def sanitize_model_headers(
    headers: Any,
    *,
    strip_secret_ref_markers: bool = False,
) -> Optional[Dict[str, str]]:
    """Sanitize configured model headers.

    Mirrors :func:`sanitizeModelHeaders``
    (``model.inline-provider.ts:63-83``).
    """
    if not headers or not isinstance(headers, dict) or isinstance(headers, list):
        return None
    out: Dict[str, str] = {}
    for header_name, header_value in headers.items():
        if not isinstance(header_value, str):
            continue
        if strip_secret_ref_markers and _IS_SECRET_REF_HEADER_VALUE_MARKER(header_value):
            continue
        out[header_name] = header_value
    return out if out else None


def _normalize_optional_lowercase_string(value: Any) -> Optional[str]:
    """Lowercase + strip; ``None`` for empty / non-string input.

    Mirrors :func:`normalizeOptionalLowercaseString`` from
    ``@openclaw/normalization-core/string-coerce``.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed.lower()


def _is_legacy_foundry_vision_model_candidate(
    *,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    model_name: Optional[str] = None,
) -> bool:
    """Return True for legacy Foundry vision-model candidates.

    Mirrors :func:`isLegacyFoundryVisionModelCandidate``
    (``model.inline-provider.ts:85-105``).
    """
    if _normalize_optional_lowercase_string(provider) != "microsoft-foundry":
        return False
    candidates: List[str] = []
    for value in (model_id, model_name):
        normalized = _normalize_optional_lowercase_string(value)
        if normalized:
            candidates.append(normalized)
    for candidate in candidates:
        if (
            candidate.startswith("gpt-")
            or candidate.startswith("o1")
            or candidate.startswith("o3")
            or candidate.startswith("o4")
            or candidate == "computer-use-preview"
        ):
            return True
    return False


def resolve_provider_model_input(
    *,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    model_name: Optional[str] = None,
    input: Any = None,
    fallback_input: Any = None,
) -> List[str]:
    """Resolve the model input modalities.

    Mirrors :func:`resolveProviderModelInput``
    (``model.inline-provider.ts:108-127``).
    """
    raw = input if isinstance(input, list) else fallback_input
    normalized: List[str] = []
    if isinstance(raw, list):
        for item in raw:
            if item == "text" or item == "image":
                normalized.append(item)
    if (
        normalized
        and "image" not in normalized
        and _is_legacy_foundry_vision_model_candidate(
            provider=provider, model_id=model_id, model_name=model_name
        )
    ):
        return ["text", "image"]
    return normalized if normalized else ["text"]


def _resolve_inline_provider_transport(
    *,
    api: Any = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve the inline provider's transport.

    Mirrors :func:`resolveInlineProviderTransport``
    (``model.inline-provider.ts:129-139``).
    """
    normalized_api = normalize_resolved_transport_api(api)
    return {
        "api": normalized_api,
        "baseUrl": (
            _NORMALIZE_GOOGLE_API_BASE_URL(base_url)
            if normalized_api == "google-generative-ai"
            else base_url
        ),
    }


def build_inline_provider_models(
    providers: Dict[str, InlineProviderConfig],
) -> List[InlineModelEntry]:
    """Build runtime model records from inline provider config.

    Mirrors :func:`buildInlineProviderModels``
    (``model.inline-provider.ts:142-196``).
    """
    out: List[InlineModelEntry] = []
    for provider_id, entry in providers.items():
        if not isinstance(provider_id, str):
            continue
        trimmed = provider_id.strip()
        if not trimmed:
            continue
        if not isinstance(entry, dict):
            continue
        provider_headers = sanitize_model_headers(
            entry.get("headers"), strip_secret_ref_markers=True
        )
        provider_request = _SANITIZE_CONFIGURED_MODEL_PROVIDER_REQUEST(
            entry.get("request")
        )
        for model in entry.get("models") or []:
            if not isinstance(model, dict):
                continue
            model_api = model.get("api") if model.get("api") is not None else entry.get("api")
            model_base_url = (
                model.get("baseUrl")
                if model.get("baseUrl") is not None
                else entry.get("baseUrl")
            )
            transport = _resolve_inline_provider_transport(
                api=model_api, base_url=model_base_url
            )
            model_headers = sanitize_model_headers(
                model.get("headers"), strip_secret_ref_markers=True
            )
            request_config = _RESOLVE_PROVIDER_REQUEST_CONFIG(
                provider=trimmed,
                api=transport.get("api") or model.get("api"),
                baseUrl=transport.get("baseUrl"),
                providerHeaders=provider_headers,
                modelHeaders=model_headers,
                authHeader=entry.get("authHeader"),
                request=provider_request,
                capability="llm",
                transport="stream",
            )
            base_url = request_config.get("baseUrl") or transport.get("baseUrl")
            api_value = request_config.get("api") or model.get("api")
            built_model: InlineModelEntry = {
                **model,
                "contextWindow": model.get("contextWindow")
                if model.get("contextWindow") is not None
                else entry.get("contextWindow"),
                "contextTokens": model.get("contextTokens")
                if model.get("contextTokens") is not None
                else entry.get("contextTokens"),
                "maxTokens": model.get("maxTokens")
                if model.get("maxTokens") is not None
                else entry.get("maxTokens"),
                "input": resolve_provider_model_input(
                    provider=trimmed,
                    model_id=model.get("id"),
                    model_name=model.get("name"),
                    input=model.get("input"),
                ),
                "provider": trimmed,
                "baseUrl": base_url,
                "api": api_value,
                "headers": request_config.get("headers"),
            }
            built_model = _ATTACH_MODEL_PROVIDER_REQUEST_TRANSPORT(
                built_model, provider_request
            )
            built_model = _ATTACH_MODEL_PROVIDER_LOCAL_SERVICE(
                built_model, entry.get("localService")
            )
            out.append(built_model)
    return out


__all__ = [
    "InlineModelEntry",
    "InlineProviderConfig",
    "SUPPORTED_TRANSPORT_APIS",
    "build_inline_provider_models",
    "normalize_resolved_transport_api",
    "resolve_provider_model_input",
    "sanitize_model_headers",
    "set_attach_model_provider_local_service_hook",
    "set_attach_model_provider_request_transport_hook",
    "set_is_secret_ref_header_value_marker_hook",
    "set_normalize_google_api_base_url_hook",
    "set_resolve_provider_request_config_hook",
    "set_sanitize_configured_model_provider_request_hook",
]
