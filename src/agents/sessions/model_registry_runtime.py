"""jarvis.agents.sessions.model_registry_runtime — per-registry runtime.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/model-registry-runtime.ts``.

The per-``ModelRegistry`` runtime facts:
the API registry + the LLM runtime. The
runtime is bound 1:1 to the owning
``ModelRegistry`` via a weak-keyed dictionary
(the same shape as the OpenClaw
``modelRegistryRuntimes`` ``WeakMap``).

Phase 6.7a — model-registry runtime.

Adaptations
-----------
- The OpenClaw source uses
  ``@openclaw/ai`` / ``@openclaw/ai/internal/runtime``
  / ``@openclaw/ai/providers`` /
  ``bindStreamLlmRuntime``. The Python port
  ships a minimal ``ApiRegistry`` placeholder
  (Phase 6.7+ wires the LLM client + the
  full built-in provider surface).
"""
from __future__ import annotations

import weakref
from typing import Any, Optional


# ============================================================================
# Minimal ApiRegistry placeholder
# ============================================================================


class ApiRegistry:
    """Placeholder for the LLM-side
    ``ApiRegistry``. Phase 6.7a ships the
    structural shape; the full provider
    surface lands in Phase 6.7+ with the LLM
    client + the built-in providers."""

    def __init__(self) -> None:
        self._providers: dict[str, Any] = {}

    def register_api_provider(self, provider: Any) -> None:
        if isinstance(provider, dict) and "id" in provider:
            self._providers[provider["id"]] = provider
        else:
            self._providers[id(provider)] = provider

    def clear_api_providers(self) -> None:
        self._providers.clear()

    def get_all(self) -> list[Any]:
        return list(self._providers.values())

    def get(self, provider_id: str) -> Optional[Any]:
        return self._providers.get(provider_id)


# ============================================================================
# Minimal LlmRuntime placeholder
# ============================================================================


class LlmRuntime:
    """Placeholder for the LLM-side
    ``LlmRuntime``. Phase 6.7a ships the
    structural shape; the full stream + model
    resolution land in Phase 6.7+."""

    def __init__(self, api_registry: ApiRegistry) -> None:
        self.api_registry = api_registry
        self.stream_simple = None  # bound later


# ============================================================================
# Per-registry runtime
# ============================================================================


#: Per-``ModelRegistry`` runtime fact. Mirrors
#: the OpenClaw source's
#: ``type ModelRegistryRuntime``
#: (``model-registry-runtime.ts:12-15``).
ModelRegistryRuntime = dict  # {"apiRegistry": ApiRegistry, "llmRuntime": LlmRuntime}


#: Weak-keyed per-instance runtime store. Mirrors
#: the OpenClaw source's
#: ``const modelRegistryRuntimes = new WeakMap<object, ModelRegistryRuntime>()``
#: (``model-registry-runtime.ts:17``).
_model_registry_runtimes: "weakref.WeakKeyDictionary[Any, ModelRegistryRuntime]" = (
    weakref.WeakKeyDictionary()
)


def _reset_api_registry(runtime: ModelRegistryRuntime) -> None:
    """Reset the api-registry to the built-in
    + plugin-published provider set.

    Phase 6.7a ships a no-op (the full
    built-in + plugin-provider surface lands
    in Phase 6.7+ with the LLM client)."""
    api_registry: ApiRegistry = runtime["apiRegistry"]
    api_registry.clear_api_providers()
    # Phase 6.7+: register the built-in
    # providers (the OpenClaw source calls
    # ``registerBuiltInApiProviders``).
    # Phase 6.7+: register the plugin-published
    # providers (the OpenClaw source iterates
    # ``getPublishedApiProviders()``).


def initialize_model_registry_runtime(owner: object) -> None:
    """Create the runtime facts owned by one
    model-registry lifecycle. Mirrors
    ``initializeModelRegistryRuntime``
    (``model-registry-runtime.ts:30-37``)."""
    api_registry = ApiRegistry()
    llm_runtime = LlmRuntime(api_registry)
    runtime: ModelRegistryRuntime = {
        "apiRegistry": api_registry,
        "llmRuntime": llm_runtime,
    }
    # Phase 6.7+: bind the stream LLM runtime.
    # llm_runtime.stream_simple = ...
    _reset_api_registry(runtime)
    _model_registry_runtimes[owner] = runtime


def get_model_registry_runtime(owner: object) -> ModelRegistryRuntime:
    """Return the prepared runtime facts for
    one model-registry lifecycle. Mirrors
    ``getModelRegistryRuntime``
    (``model-registry-runtime.ts:40-46``)."""
    runtime = _model_registry_runtimes.get(owner)
    if runtime is None:
        raise RuntimeError("Model registry runtime is not initialized")
    return runtime


def reset_model_registry_runtime(owner: object) -> None:
    """Reset the api-registry to the built-in
    + plugin-published provider set. Mirrors
    ``resetModelRegistryRuntime``
    (``model-registry-runtime.ts:48-50``)."""
    _reset_api_registry(get_model_registry_runtime(owner))


__all__ = [
    "ApiRegistry",
    "LlmRuntime",
    "ModelRegistryRuntime",
    "get_model_registry_runtime",
    "initialize_model_registry_runtime",
    "reset_model_registry_runtime",
]
