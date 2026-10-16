"""jarvis.agents.embedded_agent_runner.run.attempt_bootstrap_prepare — prepare the bootstrap context for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-bootstrap-prepare.ts``.

Public surface:

- :func:`prepare_embedded_attempt_bootstrap` (async)

Phase 7.6d-7 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Embedded-attempt bootstrap shape.
EmbeddedAttemptBootstrap = Dict[str, Any]


#: Installable hook for the prepare-bootstrap step.
_PREPARE_BOOTSTRAP: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_prepare_bootstrap_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom prepare-embedded-attempt-bootstrap hook."""
    global _PREPARE_BOOTSTRAP
    _PREPARE_BOOTSTRAP = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_attempt_bootstrap(
    params: Dict[str, Any],
) -> EmbeddedAttemptBootstrap:
    """Prepare the bootstrap context for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptBootstrap`
    (``attempt-bootstrap-prepare.ts``).
    """
    bootstrap: Any = await _maybe_await(
        _PREPARE_BOOTSTRAP(dict(params or {}))
    )
    if not isinstance(bootstrap, dict):
        bootstrap = {}
    return {
        "bootstrapFiles": bootstrap.get("bootstrapFiles") or [],
        "bootstrapPromptWarning": bootstrap.get("bootstrapPromptWarning"),
        "shouldRecordCompletedBootstrapTurn": bool(
            bootstrap.get("shouldRecordCompletedBootstrapTurn", False)
        ),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptBootstrap",
    "prepare_embedded_attempt_bootstrap",
    "set_prepare_bootstrap_hook",
]
