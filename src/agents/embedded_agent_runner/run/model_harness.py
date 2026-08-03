"""jarvis.agents.embedded_agent_runner.run.model_harness — resolve the embedded-run harness for the runtime model.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/model-harness.ts``.

Public surface:

Functions:

- :func:`resolve_embedded_run_effective_model`
- :func:`select_embedded_run_harness`
- :func:`select_embedded_run_harness_for_prepared_attempts`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the resolve-embedded-run-effective-model step.
_RESOLVE_EMBEDDED_RUN_EFFECTIVE_MODEL: Callable[
    [Dict[str, Any]], Any
] = lambda p: {"effectiveModel": p.get("runtimeModel")}


def set_resolve_embedded_run_effective_model_model_harness_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveEmbeddedRunEffectiveModel hook."""
    global _RESOLVE_EMBEDDED_RUN_EFFECTIVE_MODEL
    _RESOLVE_EMBEDDED_RUN_EFFECTIVE_MODEL = hook


#: Installable hook for the select-embedded-run-harness step.
_SELECT_EMBEDDED_RUN_HARNESS: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {"id": "openclaw", "authBootstrap": None}


def set_select_embedded_run_harness_model_harness_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom selectEmbeddedRunHarness hook."""
    global _SELECT_EMBEDDED_RUN_HARNESS
    _SELECT_EMBEDDED_RUN_HARNESS = hook


#: Installable hook for the select-embedded-run-harness-for-prepared-attempts step.
_SELECT_EMBEDDED_RUN_HARNESS_FOR_PREPARED_ATTEMPTS: Callable[
    [Dict[str, Any], Any], Any
] = lambda _m, _a: {"id": "openclaw", "authBootstrap": None}


def set_select_embedded_run_harness_for_prepared_attempts_model_harness_hook(
    hook: Callable[[Dict[str, Any], Any], Any],
) -> None:
    """Install a custom selectEmbeddedRunHarnessForPreparedAttempts hook."""
    global _SELECT_EMBEDDED_RUN_HARNESS_FOR_PREPARED_ATTEMPTS
    _SELECT_EMBEDDED_RUN_HARNESS_FOR_PREPARED_ATTEMPTS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_embedded_run_effective_model(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve the embedded-run effective model.

    Mirrors :func:`resolveEmbeddedRunEffectiveModel`
    (``model-harness.ts``).
    """
    return _RESOLVE_EMBEDDED_RUN_EFFECTIVE_MODEL(dict(params or {}))


def select_embedded_run_harness(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Select the embedded-run harness.

    Mirrors :func:`selectEmbeddedRunHarness` (``model-harness.ts``).
    """
    return _SELECT_EMBEDDED_RUN_HARNESS(dict(params or {}))


def select_embedded_run_harness_for_prepared_attempts(
    model: Dict[str, Any],
    attempts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Select the embedded-run harness for prepared attempts.

    Mirrors :func:`selectEmbeddedRunHarnessForPreparedAttempts`
    (``model-harness.ts``).
    """
    return _SELECT_EMBEDDED_RUN_HARNESS_FOR_PREPARED_ATTEMPTS(model, attempts)


__all__ = [
    "resolve_embedded_run_effective_model",
    "select_embedded_run_harness",
    "select_embedded_run_harness_for_prepared_attempts",
    "set_resolve_embedded_run_effective_model_model_harness_hook",
    "set_select_embedded_run_harness_for_prepared_attempts_model_harness_hook",
    "set_select_embedded_run_harness_model_harness_hook",
]
