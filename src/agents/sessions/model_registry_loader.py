"""jarvis.agents.sessions.model_registry_loader — agent model-registry loader.

OpenClaw parity: mirrors
``openclaw-main/src/agents/model-registry-loader.ts``.

Shared model-registry loader for agent paths
that need auth storage + plugin metadata
resolved together before model discovery.

Phase 6.7a — model-registry loader.

Adaptations
-----------
- The OpenClaw source uses
  ``discoverAuthStorage`` /
  ``discoverModels`` from
  ``./agent-model-discovery.js`` +
  ``resolveModelPluginMetadataSnapshot`` from
  ``./model-discovery-context.js`` +
  ``resolveDefaultAgentDir`` from
  ``./agent-scope.js``. The Python port ships
  minimal placeholders; the full discovery
  layer lands in Phase 6.7+ with the LLM
  client + the model-discovery context.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from .auth_storage import AuthStorage, FileAuthStorageBackend
from .model_registry import ModelRegistry


#: Mirrors ``LoadAgentModelRegistryOptions``
#: (``model-registry-loader.ts:12-18``).
#: ``providerFilter`` /
#: ``normalizeModels`` /
#: ``readOnly`` /
#: ``skipCredentials`` /
#: ``workspaceDir``.
LoadAgentModelRegistryOptions = dict


def _resolve_default_agent_dir(config: Any) -> str:
    """Return the JARVIS agent dir. Mirrors
    ``resolveDefaultAgentDir``
    (``openclaw-main/src/agents/agent-scope.js``).

    Phase 6.7a ships the JARVIS default
    (``~/.jarvis/agents/default``); the full
    agent-scope config lands in Phase 6.7+."""
    return str(
        os.path.join(os.path.expanduser("~"), ".jarvis", "agents", "default")
    )


def _discover_auth_storage(
    agent_dir: str,
    options: dict,
) -> AuthStorage:
    """Stub for ``discoverAuthStorage``. Mirrors
    the OpenClaw source's
    ``discoverAuthStorage``
    (``openclaw-main/src/agents/agent-model-discovery.ts``).

    Phase 6.7a ships a thin wrapper that
    returns a file-backed :class:`AuthStorage`
    for the agent dir. The full discovery
    layer (custom provider config fallback +
    workspace overrides) lands in Phase 6.7+.
    """
    auth_path = os.path.join(agent_dir, "auth.json")
    return AuthStorage(FileAuthStorageBackend(auth_path=auth_path))


def _discover_models(
    auth_storage: AuthStorage,
    agent_dir: str,
    options: dict,
) -> ModelRegistry:
    """Stub for ``discoverModels``. Mirrors the
    OpenClaw source's
    ``discoverModels``
    (``openclaw-main/src/agents/agent-model-discovery.ts``).

    Phase 6.7b returns a real
    :class:`ModelRegistry` (with the
    full ``models.json`` loader). The
    built-in + plugin-published providers
    + the model-discovery context land in
    Phase 6.7+."""
    workspace_dir = options.get("workspaceDir")
    return ModelRegistry.create(
        auth_storage=auth_storage,
        models_json_path=os.path.join(agent_dir, "models.json"),
        options={"workspaceDir": workspace_dir} if workspace_dir else {},
    )


def _resolve_model_plugin_metadata_snapshot(options: dict) -> Optional[Any]:
    """Stub for ``resolveModelPluginMetadataSnapshot``.
    Mirrors the OpenClaw source's
    ``resolveModelPluginMetadataSnapshot``
    (``openclaw-main/src/agents/model-discovery-context.ts``).

    Phase 6.7a returns ``None``; the full
    plugin-metadata resolution lands in
    Phase 6.7+."""
    return None


def load_agent_model_registry(
    config: Any,
    options: Optional[LoadAgentModelRegistryOptions] = None,
) -> dict:
    """Load the agent model registry with
    optional provider filtering / normalization.

    Mirrors ``loadAgentModelRegistry``
    (``model-registry-loader.ts:21-43``).

    Returns
    -------
    dict
        ``{"agentDir", "registry"}``.
    """
    options = options or {}
    agent_dir = _resolve_default_agent_dir(config)
    auth_storage = _discover_auth_storage(
        agent_dir,
        {
            "readOnly": options.get("readOnly", True),
            "skipCredentials": options.get("skipCredentials"),
            "config": config,
            "workspaceDir": options.get("workspaceDir"),
        },
    )
    plugin_metadata_snapshot = _resolve_model_plugin_metadata_snapshot(
        {"config": config, "workspaceDir": options.get("workspaceDir")}
    )
    registry = _discover_models(
        auth_storage,
        agent_dir,
        {
            "config": config,
            "pluginMetadataSnapshot": plugin_metadata_snapshot,
            "providerFilter": options.get("providerFilter"),
            "workspaceDir": options.get("workspaceDir"),
            "normalizeModels": options.get("normalizeModels"),
        },
    )
    return {"agentDir": agent_dir, "registry": registry}


__all__ = [
    "LoadAgentModelRegistryOptions",
    "load_agent_model_registry",
]
