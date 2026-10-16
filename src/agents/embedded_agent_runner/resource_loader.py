"""jarvis.agents.embedded_agent_runner.resource_loader — resource loader for embedded-agent sessions.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/resource-loader.ts``.

Public surface:

- :func:`create_embedded_agent_resource_loader`
- :data:`EMBEDDED_AGENT_RESOURCE_LOADER_DISCOVERY_OPTIONS`

Phase 7.6h-3 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict


EMBEDDED_AGENT_RESOURCE_LOADER_DISCOVERY_OPTIONS: Dict[str, bool] = {
    "noExtensions": True,
    "noSkills": True,
    "noPromptTemplates": True,
    "noThemes": True,
    "noContextFiles": True,
}


_create_embedded_agent_resource_loader_hook = None


def set_create_embedded_agent_resource_loader_hook(fn) -> None:
    global _create_embedded_agent_resource_loader_hook
    _create_embedded_agent_resource_loader_hook = fn


def create_embedded_agent_resource_loader(options: Dict[str, Any]) -> Any:
    """Create the constrained resource loader used by embedded-agent sessions.

    Mirrors :func:`createEmbeddedAgentResourceLoader` (``resource-loader.ts``).
    """
    if _create_embedded_agent_resource_loader_hook is not None:
        return _create_embedded_agent_resource_loader_hook(options)
    return {
        "options": {**options, **EMBEDDED_AGENT_RESOURCE_LOADER_DISCOVERY_OPTIONS},
    }


__all__ = [
    "EMBEDDED_AGENT_RESOURCE_LOADER_DISCOVERY_OPTIONS",
    "create_embedded_agent_resource_loader",
    "set_create_embedded_agent_resource_loader_hook",
]
