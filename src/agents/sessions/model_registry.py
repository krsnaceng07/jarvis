"""jarvis.agents.sessions.model_registry — model-registry facade.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/model-registry.ts``.

The :class:`ModelRegistry` is the public facade
the brain (Layer 1's ``createAgentSession``)
calls for model discovery + API-key
resolution. The full schema-driven
configuration surface + the model-resolution
chain land in Phase 6.7b/c.

Phase 6.7a — model-registry facade (minimal).

Adaptations
-----------
- The OpenClaw source's schema-driven
  configuration (``typebox`` Type / Compile)
  is replaced with a plain dataclass-based
  shape for Phase 6.7a. The full
  schema-validation surface lands in Phase
  6.7+ (the OpenClaw source's
  ``Compile`` validator).
- The OpenClaw source's
  ``@openclaw/ai``-backed model catalog
  + provider metadata are replaced with
  minimal placeholder shapes; the full
  catalog lands in Phase 6.7+ with the LLM
  client.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .auth_storage import AuthStorage
from .model_registry_runtime import (
    get_model_registry_runtime,
    initialize_model_registry_runtime,
    reset_model_registry_runtime,
)


_LOG = logging.getLogger("jarvis.agents.sessions.model_registry")


# ============================================================================
# Minimal placeholder shapes
# ============================================================================


#: Mirrors ``ModelDefinition``
#: (``model-registry.ts``-internal). The
#: Python port uses a plain ``dict`` for
#: Phase 6.7a; the typed shape lands in
#: Phase 6.7b.
ModelDefinition = dict


#: Mirrors ``ConfiguredModel``
#: (``model-registry.ts``-internal). The
#: Python port uses a plain ``dict`` for
#: Phase 6.7a.
ConfiguredModel = dict


# ============================================================================
# ModelRegistry
# ============================================================================


class ModelRegistry:
    """Model-registry facade. Mirrors the
    OpenClaw source's ``ModelRegistry``
    (``model-registry.ts``-export).

    Phase 6.7a ships the structural shape +
    the per-instance runtime initialisation.
    The full model discovery +
    configuration-resolution + provider
    surface lands in Phase 6.7b/c.

    Parameters
    ----------
    cwd : str
        The current working directory.
    agent_dir : str
        The agent directory
        (``~/.jarvis/agents/default`` by
        default).
    auth_storage : AuthStorage | None
        The :class:`AuthStorage` to use.
    """

    def __init__(
        self,
        cwd: str,
        agent_dir: str,
        auth_storage: Optional[AuthStorage] = None,
    ) -> None:
        self.cwd = cwd
        self.agent_dir = agent_dir
        self.auth_storage = auth_storage
        # Initialize the per-instance
        # runtime. The OpenClaw source does
        # the same in its constructor.
        try:
            initialize_model_registry_runtime(self)
        except RuntimeError:
            # Already initialized (re-init).
            reset_model_registry_runtime(self)
        self.models: list[ModelDefinition] = []
        self.configured_models: list[ConfiguredModel] = []
        self.errors: list[BaseException] = []

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @staticmethod
    def create(
        cwd: str,
        agent_dir: Optional[str] = None,
        auth_storage: Optional[AuthStorage] = None,
    ) -> "ModelRegistry":
        """Create a fresh model registry. Mirrors
        the OpenClaw source's
        ``ModelRegistry.create`` factory."""
        if agent_dir is None:
            import os
            agent_dir = str(
                __import__("pathlib").Path.home()
                / ".jarvis"
                / "agents"
                / "default"
            )
        return ModelRegistry(
            cwd=cwd,
            agent_dir=agent_dir,
            auth_storage=auth_storage,
        )

    # ------------------------------------------------------------------
    # Getters
    # ------------------------------------------------------------------

    def get_cwd(self) -> str:
        return self.cwd

    def get_agent_dir(self) -> str:
        return self.agent_dir

    def get_runtime(self) -> Any:
        """Return the per-instance runtime
        facts (``{"apiRegistry", "llmRuntime"}``).
        Mirrors the OpenClaw source's
        ``getModelRegistryRuntime``."""
        return get_model_registry_runtime(self)

    def get_models(self) -> list[ModelDefinition]:
        """Return every discovered model. Mirrors
        the OpenClaw source's
        ``getModels()``."""
        return list(self.models)

    def get_configured_models(self) -> list[ConfiguredModel]:
        """Return every configured (user-pinned)
        model. Mirrors the OpenClaw source's
        ``getConfiguredModels()``."""
        return list(self.configured_models)

    def drain_errors(self) -> list[BaseException]:
        """Drain + clear the error list. Mirrors
        the OpenClaw source's
        ``drainErrors()``."""
        drained = list(self.errors)
        self.errors = []
        return drained

    # ------------------------------------------------------------------
    # Phase 6.7b/c stubs
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Re-discover models + configured models.
        Mirrors the OpenClaw source's
        ``refresh()``.

        Phase 6.7a ships a no-op; the full
        refresh + provider discovery lands in
        Phase 6.7b."""
        return None

    def resolve_api_key(
        self, provider: str, model: Optional[str] = None
    ) -> Optional[str]:
        """Resolve an API key for a provider.
        Mirrors the OpenClaw source's
        ``resolveApiKey``.

        Phase 6.7a ships a thin wrapper around
        :meth:`AuthStorage.get_api_key`; the
        full model-aware resolution chain
        lands in Phase 6.7c."""
        if self.auth_storage is None:
            return None
        import asyncio
        return asyncio.run(self.auth_storage.get_api_key(provider))


__all__ = [
    "ConfiguredModel",
    "ModelDefinition",
    "ModelRegistry",
]
