"""plugins.embedding_provider_config — configured embedding provider aliases.

OpenClaw parity: 1:1 port of ``src/plugins/embedding-provider-config.ts``.

Reads a configured model provider's backing API id so embedding provider
runtime lookup can follow configured aliases (e.g. an OpenAI-compatible
proxy provider resolving to the generic ``openai-compatible`` adapter).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from jarvis_normalization_core.string_coerce import (
    normalize_lowercase_string_or_empty,
)


def _normalize_provider_id(provider: Any) -> str:
    """Mirrors ``normalizeProviderId`` (``model-catalog-core/provider-id.ts``)."""
    return normalize_lowercase_string_or_empty(provider)


OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_ID = "openai-compatible"
OPENAI_COMPATIBLE_MODEL_APIS = {"openai-completions", "openai-responses"}


def _resolve_configured_provider_config(
    provider_id: str,
    cfg: dict | None = None,
) -> Optional[dict]:
    """Mirrors ``resolveConfiguredProviderConfig``."""
    providers = ((cfg or {}).get("models") or {}).get("providers")
    if not isinstance(providers, dict):
        return None
    direct = providers.get(provider_id)
    if direct is not None:
        return direct
    normalized = _normalize_provider_id(provider_id)
    for candidate_id, value in providers.items():
        if _normalize_provider_id(candidate_id) == normalized:
            return value
    return None


def read_configured_provider_api_id(params: dict) -> Optional[str]:
    """Reads a configured provider's backing API id when runtime lookup
    should follow an alias.

    Mirrors ``readConfiguredProviderApiId``. ``params`` keys:
    ``providerId``, ``cfg``?, ``resolveApiProviderId``?,
    ``resolveMissingApiProviderId``?.
    """
    provider_config = _resolve_configured_provider_config(
        params["providerId"], params.get("cfg")
    )
    if not provider_config:
        return None
    normalized = _normalize_provider_id(params["providerId"])
    api_raw = provider_config.get("api")
    api = api_raw.strip() if isinstance(api_raw, str) else ""
    resolve_api: Callable[[str], Optional[str]] | None = params.get(
        "resolveApiProviderId"
    )
    resolve_missing: Callable[[dict], Optional[str]] | None = params.get(
        "resolveMissingApiProviderId"
    )
    if api:
        normalized_api = _normalize_provider_id(api)
        resolved_provider_id = (
            resolve_api(normalized_api) if resolve_api is not None else None
        ) or normalized_api
    else:
        resolved_provider_id = (
            resolve_missing(provider_config) if resolve_missing is not None else None
        )
    if resolved_provider_id and resolved_provider_id != normalized:
        return resolved_provider_id
    return None


def resolve_configured_generic_embedding_provider_id(
    provider_id: str,
    cfg: dict | None = None,
) -> Optional[str]:
    """Mirrors ``resolveConfiguredGenericEmbeddingProviderId``."""

    def _resolve_api_provider_id(normalized_api_id: str) -> Optional[str]:
        if normalized_api_id in OPENAI_COMPATIBLE_MODEL_APIS:
            return OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_ID
        return normalized_api_id

    def _resolve_missing_api_provider_id(provider_config: dict) -> Optional[str]:
        base_url = provider_config.get("baseUrl")
        if isinstance(base_url, str) and base_url.strip():
            return OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_ID
        return None

    return read_configured_provider_api_id(
        {
            "providerId": provider_id,
            "cfg": cfg,
            "resolveApiProviderId": _resolve_api_provider_id,
            "resolveMissingApiProviderId": _resolve_missing_api_provider_id,
        }
    )


__all__ = [
    "OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_ID",
    "OPENAI_COMPATIBLE_MODEL_APIS",
    "read_configured_provider_api_id",
    "resolve_configured_generic_embedding_provider_id",
]
