"""jarvis.agents.embedded_agent_runner.run.attempt_context_guards — install the context-guards for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-context-guards.ts``.

Public surface:

- :func:`install_embedded_attempt_context_guards`

Phase 7.6d-2 — focused minimal port.

The OpenClaw source is tightly coupled to the mid-turn precheck,
after-turn checkpoint, and tool-result context-guard layers. The
Python port keeps the public surface and delegates the heavy work
to installable hooks.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Embedded-attempt context-guards shape.
EmbeddedAttemptContextGuards = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the install-context-guards step.
_INSTALL_CONTEXT_GUARDS: Callable[[Dict[str, Any]], Any] = lambda _p: {}


def set_install_context_guards_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom install-context-guards hook."""
    global _INSTALL_CONTEXT_GUARDS
    _INSTALL_CONTEXT_GUARDS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def install_embedded_attempt_context_guards(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptContextGuards:
    """Install the context-guards for an attempt.

    Mirrors :func:`installEmbeddedAttemptContextGuards`
    (``attempt-context-guards.ts``).
    """
    guards: Any = _INSTALL_CONTEXT_GUARDS(dict(input_obj or {}))
    return {
        "guards": guards or {},
        "takePendingMidTurnPrecheckRequest": (
            (guards or {}).get("takePendingMidTurnPrecheckRequest")
            if isinstance(guards, dict)
            else None
        ),
        "getAfterTurnCheckpoint": (
            (guards or {}).get("getAfterTurnCheckpoint")
            if isinstance(guards, dict)
            else None
        ),
    }


__all__ = [
    "EmbeddedAttemptContextGuards",
    "install_embedded_attempt_context_guards",
    "set_install_context_guards_hook",
]
