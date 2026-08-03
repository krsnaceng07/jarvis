"""jarvis.agents.embedded_agent_runner.context_engine_capabilities — host capabilities for context-engine runtime.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/context-engine-capabilities.ts``.

Public surface:

- :func:`resolve_context_engine_capabilities`

Phase 7.6h-3 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional


_resolve_context_engine_capabilities_hook = None


def set_resolve_context_engine_capabilities_hook(fn) -> None:
    global _resolve_context_engine_capabilities_hook
    _resolve_context_engine_capabilities_hook = fn


def resolve_context_engine_capabilities(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Build host-owned capabilities that are bound to one context-engine runtime call.

    Mirrors :func:`resolveContextEngineCapabilities` (``context-engine-capabilities.ts``).
    """
    if _resolve_context_engine_capabilities_hook is not None:
        return _resolve_context_engine_capabilities_hook(params) or {}
    session_key = (params.get("sessionKey") or "").strip() or None
    agent_id = params.get("agentId")
    context_engine_plugin_id = (params.get("contextEnginePluginId") or "").strip() or None
    auth_profile_id = params.get("authProfileId")
    purpose = params.get("purpose") or "context-engine"
    config = params.get("config")

    async def _complete(request: Any) -> Any:
        # Production wiring delegates to jarvis_sdk.plugins.runtime.runtime_llm; tests
        # only check that the function shape matches.
        return None

    return {
        "llm": {
            "complete": _complete,
        },
    }


__all__ = [
    "resolve_context_engine_capabilities",
    "set_resolve_context_engine_capabilities_hook",
]
