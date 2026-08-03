"""jarvis.agents.embedded_agent_runner.run.model_setup — resolve the embedded-run model setup.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/model-setup.ts``.

Public surface:

- :func:`resolve_embedded_run_model_setup` (async)

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Embedded-run model setup shape.
EmbeddedRunModelSetup = Dict[str, Any]


#: Installable hook for the resolve-embedded-run-model-setup step.
_RESOLVE_EMBEDDED_RUN_MODEL_SETUP: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_resolve_embedded_run_model_setup_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom resolveEmbeddedRunModelSetup hook."""
    global _RESOLVE_EMBEDDED_RUN_MODEL_SETUP
    _RESOLVE_EMBEDDED_RUN_MODEL_SETUP = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def resolve_embedded_run_model_setup(
    params: Dict[str, Any],
) -> EmbeddedRunModelSetup:
    """Resolve the embedded-run model setup.

    Mirrors :func:`resolveEmbeddedRunModelSetup` (``model-setup.ts``).
    """
    setup: Any = await _maybe_await(
        _RESOLVE_EMBEDDED_RUN_MODEL_SETUP(dict(params or {}))
    )
    if not isinstance(setup, dict):
        setup = {}
    return {
        "model": setup.get("model") or {},
        "provider": setup.get("provider") or "",
        "modelId": setup.get("modelId") or "",
        "agentHarness": setup.get("agentHarness") or {
            "id": "openclaw",
            "authBootstrap": None,
        },
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedRunModelSetup",
    "resolve_embedded_run_model_setup",
    "set_resolve_embedded_run_model_setup_hook",
]
