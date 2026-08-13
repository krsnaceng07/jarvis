"""plugins.memory_embedding_providers — memory embedding provider registry.

OpenClaw parity: 1:1 port of ``src/plugins/memory-embedding-providers.ts``.

Resolves plugin-provided memory embedding providers from config and
registry. The TS source stores the registry on ``globalThis`` keyed by
``Symbol.for("openclaw.memoryEmbeddingProviders")``; the Python port
uses a process-wide module-level dict under the same key name.
"""
from __future__ import annotations

from typing import Any, TypedDict


class MemoryEmbeddingBatchChunk(TypedDict, total=False):
    """Chunk submitted to memory embedding batch processing."""

    text: str
    embeddingInput: Any


class MemoryEmbeddingBatchOptions(TypedDict, total=False):
    """Options for batch memory embedding work."""

    agentId: str
    chunks: list
    wait: bool
    concurrency: int
    pollIntervalMs: int
    timeoutMs: int
    debug: Any


class MemoryEmbeddingProviderCallOptions(TypedDict, total=False):
    """Per-call options for memory embedding providers."""

    signal: Any


class MemoryEmbeddingProviderRuntime(TypedDict, total=False):
    """Runtime metadata returned with memory embedding providers."""

    id: str
    cacheKeyData: dict
    #: Prior persisted model/cache identities equivalent to the current identity.
    indexIdentityAliases: list
    inlineQueryTimeoutMs: int
    inlineBatchTimeoutMs: int
    sourceWideBatchEmbed: bool
    batchEmbed: Any


class MemoryEmbeddingProviderIndexIdentity(TypedDict, total=False):
    """Provider-owned canonical identity and exact aliases for persisted indexes."""

    model: str
    cacheKeyData: dict
    aliases: list


class MemoryEmbeddingProvider(TypedDict, total=False):
    """Created memory embedding provider instance."""

    id: str
    model: str
    maxInputTokens: int
    embedQuery: Any
    embedBatch: Any
    embedBatchInputs: Any
    close: Any


class MemoryEmbeddingProviderCreateOptions(TypedDict, total=False):
    """Options passed to memory embedding provider adapters."""

    config: dict
    agentDir: str
    provider: str
    fallback: str
    remote: dict
    model: str
    inputType: str
    queryInputType: str
    documentInputType: str
    local: dict
    outputDimensionality: int
    #: One of RETRIEVAL_QUERY | RETRIEVAL_DOCUMENT | SEMANTIC_SIMILARITY |
    #: CLASSIFICATION | CLUSTERING | QUESTION_ANSWERING | FACT_VERIFICATION.
    taskType: str


class MemoryEmbeddingProviderCreateResult(TypedDict, total=False):
    """Result returned by a memory embedding provider adapter."""

    provider: Any  # MemoryEmbeddingProvider | None
    runtime: MemoryEmbeddingProviderRuntime


class MemoryEmbeddingProviderAdapter(TypedDict, total=False):
    """Adapter contract for registered memory embedding providers."""

    id: str
    defaultModel: str
    transport: str  # "local" | "remote"
    authProviderId: str
    autoSelectPriority: int
    allowExplicitWhenConfiguredAuto: bool
    supportsMultimodalEmbeddings: Any
    resolveIndexIdentity: Any
    create: Any
    formatSetupError: Any
    shouldContinueAutoSelection: Any


class RegisteredMemoryEmbeddingProvider(TypedDict, total=False):
    """Registered memory embedding provider with optional owning plugin metadata."""

    adapter: MemoryEmbeddingProviderAdapter
    ownerPluginId: str


MEMORY_EMBEDDING_PROVIDERS_KEY = "openclaw.memoryEmbeddingProviders"

#: Process-wide store mirroring the ``globalThis`` Map in the TS source.
_GLOBAL_STORE: dict[str, dict[str, RegisteredMemoryEmbeddingProvider]] = {}


def _get_memory_embedding_providers() -> dict[str, RegisteredMemoryEmbeddingProvider]:
    """Mirrors ``getMemoryEmbeddingProviders`` (lazy global Map)."""
    existing = _GLOBAL_STORE.get(MEMORY_EMBEDDING_PROVIDERS_KEY)
    if isinstance(existing, dict):
        return existing
    created: dict[str, RegisteredMemoryEmbeddingProvider] = {}
    _GLOBAL_STORE[MEMORY_EMBEDDING_PROVIDERS_KEY] = created
    return created


def register_memory_embedding_provider(
    adapter: MemoryEmbeddingProviderAdapter,
    options: dict[str, Any] | None = None,
) -> None:
    """Registers a memory embedding provider adapter for the current process."""
    _get_memory_embedding_providers()[adapter["id"]] = {
        "adapter": adapter,
        "ownerPluginId": (options or {}).get("ownerPluginId"),
    }


def get_registered_memory_embedding_provider(
    id: str,
) -> RegisteredMemoryEmbeddingProvider | None:
    """Returns a registered memory embedding provider entry."""
    return _get_memory_embedding_providers().get(id)


def get_memory_embedding_provider(id: str) -> MemoryEmbeddingProviderAdapter | None:
    """Returns only the memory embedding provider adapter."""
    entry = _get_memory_embedding_providers().get(id)
    return entry.get("adapter") if entry else None


def list_registered_memory_embedding_providers() -> list[RegisteredMemoryEmbeddingProvider]:
    """Lists registered memory embedding provider entries."""
    return list(_get_memory_embedding_providers().values())


def list_memory_embedding_providers() -> list[MemoryEmbeddingProviderAdapter]:
    """Lists registered memory embedding provider adapters."""
    return [entry["adapter"] for entry in list_registered_memory_embedding_providers()]


def restore_registered_memory_embedding_providers(
    entries: list[RegisteredMemoryEmbeddingProvider],
) -> None:
    """Replaces registered memory embedding providers while preserving metadata."""
    _get_memory_embedding_providers().clear()
    for entry in entries:
        register_memory_embedding_provider(
            entry["adapter"],
            {"ownerPluginId": entry.get("ownerPluginId")},
        )


def clear_memory_embedding_providers() -> None:
    """Clears registered memory embedding providers."""
    _get_memory_embedding_providers().clear()


__all__ = [
    "MemoryEmbeddingBatchChunk",
    "MemoryEmbeddingBatchOptions",
    "MemoryEmbeddingProviderCallOptions",
    "MemoryEmbeddingProviderRuntime",
    "MemoryEmbeddingProviderIndexIdentity",
    "MemoryEmbeddingProvider",
    "MemoryEmbeddingProviderCreateOptions",
    "MemoryEmbeddingProviderCreateResult",
    "MemoryEmbeddingProviderAdapter",
    "RegisteredMemoryEmbeddingProvider",
    "MEMORY_EMBEDDING_PROVIDERS_KEY",
    "register_memory_embedding_provider",
    "get_registered_memory_embedding_provider",
    "get_memory_embedding_provider",
    "list_registered_memory_embedding_providers",
    "list_memory_embedding_providers",
    "restore_registered_memory_embedding_providers",
    "clear_memory_embedding_providers",
]
