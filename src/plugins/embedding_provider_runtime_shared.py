"""plugins.embedding_provider_runtime_shared — shared embedding lookup.

OpenClaw parity: 1:1 port of
``src/plugins/embedding-provider-runtime-shared.ts``.

Shared runtime helpers for embedding provider lookup across core and
plugin capabilities.

Port note: the TS source's fallback path goes through
``capability-provider-runtime.ts`` (``resolvePluginCapabilityProvider`` /
``resolvePluginCapabilityProviders``). That module is not ported yet, so
the fallback is routed through a seam (:func:`_resolve_plugin_capability_provider`
/ :func:`_resolve_plugin_capability_providers`) that resolves to
no-capability results until the capability runtime lands. The registered-
provider-first ordering is identical to the source.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from jarvis_normalization_core.string_coerce import (
    normalize_lowercase_string_or_empty,
)


def _normalize_provider_id(provider: Any) -> str:
    """Mirrors ``normalizeProviderId`` (``model-catalog-core/provider-id.ts``)."""
    return normalize_lowercase_string_or_empty(provider)


def _resolve_plugin_capability_providers(params: dict) -> list:
    """Seam for ``resolvePluginCapabilityProviders``.

    ``capability-provider-runtime.ts`` is unported; behave as if no
    plugin contributes capability adapters (the source's result when the
    manifest/registry surface is empty).
    """
    try:  # pragma: no cover - exercised once the capability runtime lands
        from .capability_provider_runtime import (  # type: ignore[attr-defined]
            resolve_plugin_capability_providers,
        )
    except ImportError:
        return []
    return resolve_plugin_capability_providers(params)


def _resolve_plugin_capability_provider(params: dict) -> Any:
    """Seam for ``resolvePluginCapabilityProvider`` (see above)."""
    try:  # pragma: no cover - exercised once the capability runtime lands
        from .capability_provider_runtime import (  # type: ignore[attr-defined]
            resolve_plugin_capability_provider,
        )
    except ImportError:
        return None
    return resolve_plugin_capability_provider(params)


def resolve_runtime_embedding_provider_lookup_ids(params: dict) -> list[str]:
    """Builds lookup ids for embedding providers, including configured API aliases.

    Mirrors ``resolveRuntimeEmbeddingProviderLookupIds``. ``params`` keys:
    ``id``, ``cfg``?, ``resolveConfiguredProviderId``.
    """
    ids: list[str] = [params["id"]]
    resolve_configured: Callable[[str, Optional[dict]], Optional[str]] = params[
        "resolveConfiguredProviderId"
    ]
    configured_provider_id = resolve_configured(params["id"], params.get("cfg"))
    if configured_provider_id and not any(
        _normalize_provider_id(candidate) == configured_provider_id
        for candidate in ids
    ):
        ids.append(configured_provider_id)
    return ids


def list_runtime_embedding_provider_adapters(params: dict) -> list:
    """Lists registered and plugin-contributed embedding provider adapters
    for a capability key.

    Mirrors ``listRuntimeEmbeddingProviderAdapters``. ``params`` keys:
    ``key`` ("embeddingProviders" | "memoryEmbeddingProviders"),
    ``cfg``?, ``registered`` (list of adapters with ``id``).
    """
    merged: dict[str, Any] = {
        adapter["id"]: adapter for adapter in params["registered"]
    }
    capability_adapters = _resolve_plugin_capability_providers(
        {"key": params["key"], "cfg": params.get("cfg")}
    )
    for adapter in capability_adapters:
        if adapter["id"] not in merged:
            merged[adapter["id"]] = adapter
    return list(merged.values())


def get_runtime_embedding_provider_adapter(params: dict) -> Any:
    """Resolves one embedding provider adapter from registered providers
    before plugin capabilities.

    Mirrors ``getRuntimeEmbeddingProviderAdapter``. ``params`` keys:
    ``key``, ``cfg``?, ``lookupIds``, ``getRegisteredProvider``.
    """
    get_registered: Callable[[str], Any] = params["getRegisteredProvider"]
    for candidate_id in params["lookupIds"]:
        registered = get_registered(candidate_id)
        if registered:
            return registered["adapter"]
    for candidate_id in params["lookupIds"]:
        provider = _resolve_plugin_capability_provider(
            {
                "key": params["key"],
                "providerId": candidate_id,
                "cfg": params.get("cfg"),
            }
        )
        if provider:
            return provider
    return None


__all__ = [
    "resolve_runtime_embedding_provider_lookup_ids",
    "list_runtime_embedding_provider_adapters",
    "get_runtime_embedding_provider_adapter",
]
