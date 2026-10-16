"""jarvis.agents.embedded_agent_runner.run.attempt_setup — prepare the setup for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-setup.ts``.

Public surface:

- :func:`prepare_embedded_attempt_setup` (async)

Phase 7.6d-7 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Embedded-attempt setup shape.
EmbeddedAttemptSetup = Dict[str, Any]


#: RunEmbeddedAgentParams shape (re-exported).
EmbeddedRunAttemptParams = Dict[str, Any]


#: Installable hook for the prepare-setup step.
_PREPARE_SETUP: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_prepare_setup_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom prepare-embedded-attempt-setup hook."""
    global _PREPARE_SETUP
    _PREPARE_SETUP = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_attempt_setup(
    params: EmbeddedRunAttemptParams,
) -> EmbeddedAttemptSetup:
    """Prepare the setup for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptSetup`
    (``attempt-setup.ts``).
    """
    setup: Any = await _maybe_await(
        _PREPARE_SETUP(dict(params or {}))
    )
    if not isinstance(setup, dict):
        setup = {}
    return {
        "sessionAgentId": setup.get("sessionAgentId"),
        "effectiveWorkspace": setup.get("effectiveWorkspace"),
        "effectiveFsWorkspaceOnly": bool(
            setup.get("effectiveFsWorkspaceOnly", False)
        ),
        "sandbox": setup.get("sandbox"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptSetup",
    "EmbeddedRunAttemptParams",
    "prepare_embedded_attempt_setup",
    "set_prepare_setup_hook",
]
