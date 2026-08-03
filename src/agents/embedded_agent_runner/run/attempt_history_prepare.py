"""jarvis.agents.embedded_agent_runner.run.attempt_history_prepare — prepare the history for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-history-prepare.ts``.

Public surface:

- :func:`prepare_embedded_attempt_history` (async)

Phase 7.6d-4 — focused minimal port.

The OpenClaw source is tightly coupled to the context-engine
history loading, history-image-prune, and transcript
replay layers. The Python port keeps the public surface and
delegates the heavy work to installable hooks.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Embedded-attempt history shape.
EmbeddedAttemptHistory = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the load-context-engine-history step.
_LOAD_CONTEXT_ENGINE_HISTORY: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_load_context_engine_history_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom load-context-engine-history hook."""
    global _LOAD_CONTEXT_ENGINE_HISTORY
    _LOAD_CONTEXT_ENGINE_HISTORY = hook


#: Hook for the prune-history-images step.
_PRUNE_HISTORY_IMAGES: Callable[[Dict[str, Any]], Any] = lambda _p: None


def set_prune_history_images_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom prune-history-images hook."""
    global _PRUNE_HISTORY_IMAGES
    _PRUNE_HISTORY_IMAGES = hook


#: Hook for the prepare-history-replay step.
_PREPARE_HISTORY_REPLAY: Callable[[Dict[str, Any]], Any] = lambda _p: None


def set_prepare_history_replay_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom prepare-history-replay hook."""
    global _PREPARE_HISTORY_REPLAY
    _PREPARE_HISTORY_REPLAY = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_attempt_history(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptHistory:
    """Prepare the history for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptHistory`
    (``attempt-history-prepare.ts``).
    """
    history: Any = await _maybe_await(
        _LOAD_CONTEXT_ENGINE_HISTORY(dict(input_obj or {}))
    )
    if not isinstance(history, dict):
        history = {}
    pruned = _PRUNE_HISTORY_IMAGES(
        {"history": history, "input": input_obj}
    )
    replay = _PREPARE_HISTORY_REPLAY(
        {"history": pruned if pruned is not None else history, "input": input_obj}
    )
    return {
        "messages": (pruned if pruned is not None else history).get(
            "messages"
        ) or [],
        "replay": replay,
        "summary": (pruned if pruned is not None else history).get("summary"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptHistory",
    "prepare_embedded_attempt_history",
    "set_load_context_engine_history_hook",
    "set_prepare_history_replay_hook",
    "set_prune_history_images_hook",
]
