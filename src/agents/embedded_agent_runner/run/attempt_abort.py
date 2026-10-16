"""jarvis.agents.embedded_agent_runner.run.attempt_abort — create attempt abort controllers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-abort.ts``.

Public surface:

Types:

- :data:`EmbeddedAttemptAbortStatePort`

Functions:

- :func:`create_embedded_attempt_external_abort_controller`
- :func:`create_embedded_attempt_run_abort`

Phase 7.6d-2 — focused minimal port.

The OpenClaw source is tightly coupled to the abortable, abort-
controller, and run-abort-controller layers. The Python port keeps
the public surface and delegates the heavy work to installable
hooks.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Embedded-attempt abort state port. Mirrors
#: :class:`EmbeddedAttemptAbortStatePort` (``attempt-abort.ts``).
EmbeddedAttemptAbortStatePort = Dict[str, Any]


#: External-abort controller.
EmbeddedAttemptExternalAbortController = Dict[str, Any]


#: Run-abort controller.
EmbeddedAttemptRunAbort = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the create-external-abort-controller step.
_CREATE_EXTERNAL_ABORT_CONTROLLER: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_create_external_abort_controller_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom create-external-abort-controller hook."""
    global _CREATE_EXTERNAL_ABORT_CONTROLLER
    _CREATE_EXTERNAL_ABORT_CONTROLLER = hook


#: Hook for the create-run-abort-controller step.
_CREATE_RUN_ABORT_CONTROLLER: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_create_run_abort_controller_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom create-run-abort-controller hook."""
    global _CREATE_RUN_ABORT_CONTROLLER
    _CREATE_RUN_ABORT_CONTROLLER = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_embedded_attempt_external_abort_controller(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptExternalAbortController:
    """Create the external abort controller for an attempt.

    Mirrors :func:`createEmbeddedAttemptExternalAbortController`
    (``attempt-abort.ts``).
    """
    controller: Any = _CREATE_EXTERNAL_ABORT_CONTROLLER(dict(input_obj or {}))
    return {
        "controller": controller,
        "signal": input_obj.get("signal"),
        "externalAbort": bool(input_obj.get("externalAbort")),
    }


def create_embedded_attempt_run_abort(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptRunAbort:
    """Create the run-abort controller for an attempt.

    Mirrors :func:`createEmbeddedAttemptRunAbort`
    (``attempt-abort.ts``).
    """
    controller: Any = _CREATE_RUN_ABORT_CONTROLLER(dict(input_obj or {}))
    return {
        "controller": controller,
        "aborted": bool(input_obj.get("aborted")),
        "externalAbort": bool(input_obj.get("externalAbort")),
    }


__all__ = [
    "EmbeddedAttemptAbortStatePort",
    "EmbeddedAttemptExternalAbortController",
    "EmbeddedAttemptRunAbort",
    "create_embedded_attempt_external_abort_controller",
    "create_embedded_attempt_run_abort",
    "set_create_external_abort_controller_hook",
    "set_create_run_abort_controller_hook",
]
