"""jarvis_sdk.memory_embeddings — embedding provider adapter contract.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/openclaw-runtime-memory.ts``'s
``MemoryEmbeddingProvider`` and the ``getMemoryEmbeddingProvider``
registry.

Used by ``memory-lancedb`` (and any future vector backend) to
fetch an embedding provider by id (``openai``, ``github-copilot``,
``ollama``, etc.) and embed text into vectors.

Architecture
============
OpenClaw's embedding provider layer is a registry: the host
exposes ``getMemoryEmbeddingProvider(provider_id, config)``;
the plugin picks an id and uses the returned provider. The
Python port mirrors this with a tiny registry that the host
pre-populates at startup.

Parity
======
- ``MemoryEmbeddingProvider`` is an ABC with
  ``embed_query(text, options)`` and
  ``embed_batch(chunks, options)``.
- ``register_memory_embedding_provider(id, factory)`` adds an
  adapter to the process-wide registry.
- ``get_memory_embedding_provider(id, config)`` returns the
  adapter's ``MemoryEmbeddingProvider`` instance, or None.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MemoryEmbeddingProvider(ABC):
    """Abstract embedding provider. Mirrors OpenClaw's contract.

    ``embed_query`` is the hot path; ``embed_batch`` is the
    bulk indexer (OpenClaw has a separate batch runner for
    the embedding-batch OpenAI endpoint — Phase 4.0 ships the
    single-query path; the batch path is Phase 4.1+).
    """

    @abstractmethod
    async def embed_query(
        self,
        text: str,
        options: dict[str, Any] | None = None,
    ) -> list[float]: ...

    async def embed_batch(
        self,
        chunks: list[str],
        options: dict[str, Any] | None = None,
    ) -> list[list[float]]:
        """Default: one-at-a-time. Backends can override."""
        return [await self.embed_query(c, options) for c in chunks]


_REGISTRY: dict[str, MemoryEmbeddingProviderAdapter] = {}


class MemoryEmbeddingProviderAdapter(ABC):
    """Adapter that produces a configured provider for a (config, agent).

    Mirrors OpenClaw's ``MemoryEmbeddingProviderAdapter``. The
    host pre-populates the registry; ``get_memory_embedding_provider``
    delegates to the matching adapter's ``create`` to obtain a
    ready-to-use provider.
    """

    id: str = ""

    @abstractmethod
    async def create(
        self,
        config: dict[str, Any] | None = None,
        *,
        agent_dir: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        **options: Any,
    ) -> MemoryEmbeddingProvider | None: ...


def register_memory_embedding_provider(
    id: str,
    adapter: MemoryEmbeddingProviderAdapter,
) -> None:
    """Register an embedding provider adapter by id."""
    if not id:
        raise ValueError("provider id must be a non-empty string")
    _REGISTRY[id] = adapter


def get_memory_embedding_provider(
    id: str,
    config: dict[str, Any] | None = None,
) -> MemoryEmbeddingProviderAdapter | None:
    """Look up a registered provider adapter. Returns None if unknown."""
    return _REGISTRY.get(id)


def list_registered_memory_embedding_providers() -> list[str]:
    """Return the list of registered provider ids (sorted)."""
    return sorted(_REGISTRY.keys())


__all__ = [
    "MemoryEmbeddingProvider",
    "MemoryEmbeddingProviderAdapter",
    "get_memory_embedding_provider",
    "list_registered_memory_embedding_providers",
    "register_memory_embedding_provider",
]
