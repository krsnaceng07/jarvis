"""plugins.memory_embedding_provider_runtime — runtime bridge for
plugin-provided memory embedding providers.

OpenClaw parity: 1:1 port of
``src/plugins/memory-embedding-provider-runtime.ts``.
"""
from __future__ import annotations

from typing import Optional

from .embedding_provider_config import read_configured_provider_api_id
from .embedding_provider_runtime_shared import (
    get_runtime_embedding_provider_adapter,
    list_runtime_embedding_provider_adapters,
    resolve_runtime_embedding_provider_lookup_ids,
)
from .memory_embedding_providers import (
    MemoryEmbeddingProviderAdapter,
    get_registered_memory_embedding_provider,
    list_registered_memory_embedding_providers,
)

__all__ = [
    "list_registered_memory_embedding_providers",
    "list_registered_memory_embedding_provider_adapters",
    "list_memory_embedding_providers",
    "get_memory_embedding_provider",
]


def list_registered_memory_embedding_provider_adapters() -> list[
    MemoryEmbeddingProviderAdapter
]:
    """Lists registered memory embedding provider adapters without registry metadata."""
    return [
        entry["adapter"] for entry in list_registered_memory_embedding_providers()
    ]


def list_memory_embedding_providers(
    cfg: dict | None = None,
) -> list[MemoryEmbeddingProviderAdapter]:
    """Lists memory embedding providers from runtime config and registered adapters."""
    return list_runtime_embedding_provider_adapters(
        {
            "key": "memoryEmbeddingProviders",
            "cfg": cfg,
            "registered": list_registered_memory_embedding_provider_adapters(),
        }
    )


def _resolve_configured_memory_embedding_provider_id(
    provider_id: str,
    cfg: dict | None = None,
) -> Optional[str]:
    """Mirrors ``resolveConfiguredMemoryEmbeddingProviderId``."""
    return read_configured_provider_api_id({"providerId": provider_id, "cfg": cfg})


def _resolve_memory_embedding_provider_lookup_ids(
    id: str,
    cfg: dict | None = None,
) -> list[str]:
    """Mirrors ``resolveMemoryEmbeddingProviderLookupIds``."""
    return resolve_runtime_embedding_provider_lookup_ids(
        {
            "id": id,
            "cfg": cfg,
            "resolveConfiguredProviderId": _resolve_configured_memory_embedding_provider_id,
        }
    )


def get_memory_embedding_provider(
    id: str,
    cfg: dict | None = None,
) -> Optional[MemoryEmbeddingProviderAdapter]:
    """Resolves one memory embedding provider by id, alias, or configured API owner."""
    return get_runtime_embedding_provider_adapter(
        {
            "key": "memoryEmbeddingProviders",
            "cfg": cfg,
            "lookupIds": _resolve_memory_embedding_provider_lookup_ids(id, cfg),
            "getRegisteredProvider": get_registered_memory_embedding_provider,
        }
    )
