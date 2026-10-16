"""jarvis.agents.embedded_agent_runner.run.runtime_preparation — prepare the embedded-run runtime.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/runtime-preparation.ts``.

Public surface:

- :func:`prepare_embedded_run_runtime` (async) — assemble the
  model-setup, auth-plan, harness, and runtime-model state for the
  run.

Phase 7.6b-3 — focused minimal port.

The OpenClaw source is tightly coupled to the model-setup,
auth-plan, harness-selection, runtime-resolution, and stage-tracking
layers. The Python port keeps the public surface and delegates the
heavy work to installable hooks.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Embedded run model setup result.
EmbeddedRunModelSetup = Dict[str, Any]


#: Auth profile store shape.
AuthProfileStore = Dict[str, Any]


#: Embedded run auth plan.
EmbeddedRunAuthPlan = Dict[str, Any]


#: Embedded run effective model.
EmbeddedRunEffectiveModel = Dict[str, Any]


#: Runtime auth state.
RuntimeAuthState = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for :func:`resolveEmbeddedRunModelSetup` from
#: ``model-setup.ts``.
_RESOLVE_EMBEDDED_RUN_MODEL_SETUP: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_resolve_embedded_run_model_setup_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom resolveEmbeddedRunModelSetup hook."""
    global _RESOLVE_EMBEDDED_RUN_MODEL_SETUP
    _RESOLVE_EMBEDDED_RUN_MODEL_SETUP = hook


#: Hook for :func:`resolveEmbeddedRunEffectiveModel` from
#: ``model-harness.ts``.
_RESOLVE_EMBEDDED_RUN_EFFECTIVE_MODEL: Callable[
    [Dict[str, Any]], EmbeddedRunEffectiveModel
] = lambda p: {
    "effectiveModel": p.get("runtimeModel"),
    "contextWindowInfo": None,
    "contextTokenBudget": None,
}


def set_resolve_embedded_run_effective_model_hook(
    hook: Callable[[Dict[str, Any]], EmbeddedRunEffectiveModel],
) -> None:
    """Install a custom resolveEmbeddedRunEffectiveModel hook."""
    global _RESOLVE_EMBEDDED_RUN_EFFECTIVE_MODEL
    _RESOLVE_EMBEDDED_RUN_EFFECTIVE_MODEL = hook


#: Hook for :func:`selectEmbeddedRunHarness` from ``model-harness.ts``.
_SELECT_EMBEDDED_RUN_HARNESS: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {"id": "openclaw", "authBootstrap": None}


def set_select_embedded_run_harness_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom selectEmbeddedRunHarness hook."""
    global _SELECT_EMBEDDED_RUN_HARNESS
    _SELECT_EMBEDDED_RUN_HARNESS = hook


#: Hook for :func:`selectEmbeddedRunHarnessForPreparedAttempts` from
#: ``model-harness.ts``.
_SELECT_EMBEDDED_RUN_HARNESS_FOR_PREPARED_ATTEMPTS: Callable[
    [Dict[str, Any], Any], Any
] = lambda _m, _attempts: {"id": "openclaw", "authBootstrap": None}


def set_select_embedded_run_harness_for_prepared_attempts_hook(
    hook: Callable[[Dict[str, Any], Any], Any],
) -> None:
    """Install a custom selectEmbeddedRunHarnessForPreparedAttempts hook."""
    global _SELECT_EMBEDDED_RUN_HARNESS_FOR_PREPARED_ATTEMPTS
    _SELECT_EMBEDDED_RUN_HARNESS_FOR_PREPARED_ATTEMPTS = hook


#: Hook for :func:`resolveInitialThinkLevel` from
#: ``runtime-resolution.ts``.
_RESOLVE_INITIAL_THINK_LEVEL: Callable[[Dict[str, Any]], str] = lambda _p: "medium"


def set_resolve_initial_think_level_hook(
    hook: Callable[[Dict[str, Any]], str],
) -> None:
    """Install a custom resolveInitialThinkLevel hook."""
    global _RESOLVE_INITIAL_THINK_LEVEL
    _RESOLVE_INITIAL_THINK_LEVEL = hook


#: Hook for the canRunPreparedAgentRuntimeAuthAttempt step.
_CAN_RUN_PREPARED_AGENT_RUNTIME_AUTH_ATTEMPT: Callable[
    [Dict[str, Any]], bool
] = lambda _p: True


def set_can_run_prepared_agent_runtime_auth_attempt_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom canRunPreparedAgentRuntimeAuthAttempt hook."""
    global _CAN_RUN_PREPARED_AGENT_RUNTIME_AUTH_ATTEMPT
    _CAN_RUN_PREPARED_AGENT_RUNTIME_AUTH_ATTEMPT = hook


#: Hook for the hasPreparedAuthAttemptModelMetadata step.
_HAS_PREPARED_AUTH_ATTEMPT_MODEL_METADATA: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_has_prepared_auth_attempt_model_metadata_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom hasPreparedAuthAttemptModelMetadata hook."""
    global _HAS_PREPARED_AUTH_ATTEMPT_MODEL_METADATA
    _HAS_PREPARED_AUTH_ATTEMPT_MODEL_METADATA = hook


#: Hook for the createEmbeddedRunStageTracker step.
_CREATE_EMBEDDED_RUN_STAGE_TRACKER: Callable[[], Any] = lambda: {}


def set_create_embedded_run_stage_tracker_hook(
    hook: Callable[[], Any],
) -> None:
    """Install a custom createEmbeddedRunStageTracker hook."""
    global _CREATE_EMBEDDED_RUN_STAGE_TRACKER
    _CREATE_EMBEDDED_RUN_STAGE_TRACKER = hook


#: Hook for the formatEmbeddedRunStageSummary step.
_FORMAT_EMBEDDED_RUN_STAGE_SUMMARY: Callable[[Any], str] = lambda _tracker: ""


def set_format_embedded_run_stage_summary_hook(
    hook: Callable[[Any], str],
) -> None:
    """Install a custom formatEmbeddedRunStageSummary hook."""
    global _FORMAT_EMBEDDED_RUN_STAGE_SUMMARY
    _FORMAT_EMBEDDED_RUN_STAGE_SUMMARY = hook


#: Hook for the isProfileInCooldown step.
_IS_PROFILE_IN_COOLDOWN: Callable[[Any, str, Any, str], bool] = (
    lambda _store, _profile, _u, _model: False
)


def set_is_profile_in_cooldown_runtime_hook(
    hook: Callable[[Any, str, Any, str], bool],
) -> None:
    """Install a custom isProfileInCooldown hook."""
    global _IS_PROFILE_IN_COOLDOWN
    _IS_PROFILE_IN_COOLDOWN = hook


#: Hook for the resolveCandidateThinkingLevel step.
_RESOLVE_CANDIDATE_THINKING_LEVEL: Callable[[Dict[str, Any]], str] = lambda _p: "medium"


def set_resolve_candidate_thinking_level_hook(
    hook: Callable[[Dict[str, Any]], str],
) -> None:
    """Install a custom resolveCandidateThinkingLevel hook."""
    global _RESOLVE_CANDIDATE_THINKING_LEVEL
    _RESOLVE_CANDIDATE_THINKING_LEVEL = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_run_runtime(
    input_obj: Dict[str, Any],
) -> Dict[str, Any]:
    """Prepare the embedded-run runtime state.

    Mirrors :func:`prepareEmbeddedRunRuntime`
    (``runtime-preparation.ts:38-...``).
    """
    run_params = input_obj.get("runParams") or {}
    provider = input_obj.get("provider") or ""
    model_id = input_obj.get("modelId") or ""
    mark_startup_stage = input_obj.get("markStartupStage")

    model_setup = await _maybe_await(
        _RESOLVE_EMBEDDED_RUN_MODEL_SETUP(
            {
                "runParams": run_params,
                "provider": provider,
                "modelId": model_id,
                "agentDir": input_obj.get("agentDir") or "",
                "workspaceDir": input_obj.get("workspaceDir") or "",
                "globalLane": input_obj.get("globalLane") or "",
                "hookRunner": input_obj.get("hookRunner"),
                "hookContext": input_obj.get("hookContext") or {},
                "onHooksResolved": (
                    lambda: mark_startup_stage("hooks")
                    if callable(mark_startup_stage)
                    else None
                ),
            }
        )
    )
    if not isinstance(model_setup, dict):
        model_setup = {}
    provider = model_setup.get("provider") or provider
    model_id = model_setup.get("modelId") or model_id
    agent_harness = model_setup.get("agentHarness") or {
        "id": "openclaw",
        "authBootstrap": None,
    }
    runtime_model = model_setup.get("model") or {}
    initial_think_level = _RESOLVE_INITIAL_THINK_LEVEL(
        {
            "runParams": run_params,
            "provider": provider,
            "modelId": model_id,
        }
    )

    return {
        "provider": provider,
        "modelId": model_id,
        "agentHarness": agent_harness,
        "runtimeModel": runtime_model,
        "modelSetup": model_setup,
        "initialThinkLevel": initial_think_level,
        "contextTokenBudget": None,
        "contextWindowInfo": None,
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "AuthProfileStore",
    "EmbeddedRunAuthPlan",
    "EmbeddedRunEffectiveModel",
    "EmbeddedRunModelSetup",
    "RuntimeAuthState",
    "prepare_embedded_run_runtime",
    "set_can_run_prepared_agent_runtime_auth_attempt_hook",
    "set_create_embedded_run_stage_tracker_hook",
    "set_format_embedded_run_stage_summary_hook",
    "set_has_prepared_auth_attempt_model_metadata_hook",
    "set_is_profile_in_cooldown_runtime_hook",
    "set_resolve_candidate_thinking_level_hook",
    "set_resolve_embedded_run_effective_model_hook",
    "set_resolve_embedded_run_model_setup_hook",
    "set_resolve_initial_think_level_hook",
    "set_select_embedded_run_harness_for_prepared_attempts_hook",
    "set_select_embedded_run_harness_hook",
]
