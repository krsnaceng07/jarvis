"""jarvis.agents.embedded_agent_runner.run_orchestrator — the run orchestrator.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run-orchestrator.ts``.

Public surface (mirrors the OpenClaw
source):

- :func:`run_embedded_agent` —
  the public entrypoint (re-exported
  from :mod:`.run`).
- :func:`run_embedded_agent_internal` —
  the internal orchestrator (private
  to the module).

Phase 7.1 — focused minimal port.
The full implementation (with
hooks, plugins, session bootstrap,
CLI backend dispatch, lane
control, etc.) lands in 7.2+
(when the specialized sub-modules
are ported)."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Coroutine, Iterator, Optional, TypeVar, cast

from jarvis_normalization_core.string_coerce import normalize_optional_string
from jarvis_sdk.agent_runtime import resolve_agent_workspace_dir

from src.config.io import get_runtime_config_snapshot

from .lanes import resolve_session_lane
from .logger import log
from .run.execution_context import PreparedEmbeddedRunInput
from .run.internal_params import (
    RunEmbeddedAgentInternalParams,
    RunEmbeddedAgentParamsWithSessionFile,
)
from .run.session_target import (
    apply_agent_run_session_target_identity,
    resolve_agent_run_session_target,
)
from .run.workspace_run import resolve_run_workspace_dir
from .run_loop import run_prepared_embedded_loop
from .types import EmbeddedAgentRunResult


_LOG = logging.getLogger(
    "jarvis.agents.embedded_agent_runner.run_orchestrator"
)

_AGENT_RUN_LIFECYCLE_GENERATION = 0
_T = TypeVar("_T")


def capture_agent_run_lifecycle_generation(run_id: Optional[str] = None) -> int:
    """Capture the next lifecycle-generation value for a run.

    Mirrors the OpenClaw lifecycle-generation contract, which increments on
    each new run attempt and keeps the value available to downstream hooks.
    """
    global _AGENT_RUN_LIFECYCLE_GENERATION
    _AGENT_RUN_LIFECYCLE_GENERATION += 1
    return _AGENT_RUN_LIFECYCLE_GENERATION


def get_agent_event_lifecycle_generation() -> int:
    """Return the current lifecycle-generation value for the active context."""
    return _AGENT_RUN_LIFECYCLE_GENERATION


@contextmanager
def with_agent_run_lifecycle_generation(generation: int) -> Iterator[None]:
    """Temporarily install a lifecycle-generation value for the active context."""
    global _AGENT_RUN_LIFECYCLE_GENERATION
    previous = _AGENT_RUN_LIFECYCLE_GENERATION
    _AGENT_RUN_LIFECYCLE_GENERATION = generation
    try:
        yield
    finally:
        _AGENT_RUN_LIFECYCLE_GENERATION = previous


def run_embedded_agent(
    params_input: Any,
) -> EmbeddedAgentRunResult | Coroutine[Any, Any, EmbeddedAgentRunResult]:
    """The public embedded-agent run
    entrypoint. Mirrors
    :func:`runEmbeddedAgent`
    (``run-orchestrator.ts:59-80``).

    Phase 7.1 — focused minimal port.
    The full lifecycle (lifecycle
    generation capture, runtime
    config snapshot, CLI backend
    dispatch, hooks, etc.) lands in
    7.2+ (when the specialized
    sub-modules are ported).
    """
    internal: RunEmbeddedAgentInternalParams = (
        RunEmbeddedAgentInternalParams(**(params_input or {}))
    )
    requested_provider = normalize_optional_string(internal.get("provider"))
    requested_model = normalize_optional_string(internal.get("model"))
    needs_configured_default = (
        not internal.get("config")
        and not requested_provider
        and not requested_model
    )
    config = internal.get("config") or (
        get_runtime_config_snapshot() if needs_configured_default else None
    )
    lifecycle_generation = internal.get("lifecycleGeneration") or capture_agent_run_lifecycle_generation(
        internal.get("runId")
    )

    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    with with_agent_run_lifecycle_generation(lifecycle_generation):
        if loop is not None:
            return _run_embedded_agent_internal_async(
                RunEmbeddedAgentInternalParams(
                    {
                        **internal,
                        "config": config,
                        "lifecycleGeneration": lifecycle_generation,
                    }
                )
            )
        return asyncio.run(
            _run_embedded_agent_internal_async(
                RunEmbeddedAgentInternalParams(
                    {
                        **internal,
                        "config": config,
                        "lifecycleGeneration": lifecycle_generation,
                    }
                )
            )
        )


async def _run_embedded_agent_internal_async(
    params_input: RunEmbeddedAgentInternalParams,
) -> EmbeddedAgentRunResult:
    """The internal orchestrator.
    Mirrors
    :func:`runEmbeddedAgentInternal`
    (``run-orchestrator.ts:82-310`).

    Phase 7.1 — focused minimal port:
    1. Resolve the session key.
    2. Build the lane controllers.
    3. Prepare the input.
    4. Invoke the main loop.
    """
    started = int(time.time() * 1000)
    params_base: dict[str, Any] = apply_agent_run_session_target_identity(
        dict(params_input)
    )
    config_raw = params_base.get("config")
    config_dict = (
        cast(dict[str, Any], config_raw)
        if isinstance(config_raw, dict)
        else None
    )
    provider = normalize_optional_string(
        params_base.get("provider")
    ) or normalize_optional_string(
        config_dict.get("provider") if config_dict else None
    ) or "default"
    model_id = normalize_optional_string(
        params_base.get("model")
    ) or normalize_optional_string(
        config_dict.get("model") if config_dict else None
    ) or "default"
    # Resolve the session key early so all downstream consumers receive a
    # stable sessionKey even when callers omit it.
    session_key = (
        normalize_optional_string(params_base.get("sessionKey"))
        or normalize_optional_string(params_base.get("sessionId"))
        or "default"
    )
    session_id = normalize_optional_string(params_base.get("sessionId")) or session_key
    run_session_target = resolve_agent_run_session_target(
        {
            **params_base,
            "sessionKey": session_key,
            "sessionId": session_id,
        }
    )
    resolved_agent_id = normalize_optional_string(run_session_target.get("agentId")) or ""
    resolved_session_key = normalize_optional_string(run_session_target.get("sessionKey")) or session_key
    resolved_session_id = normalize_optional_string(run_session_target.get("sessionId")) or session_id
    session_file = normalize_optional_string(run_session_target.get("sessionFile")) or ""
    _session_lane = resolve_session_lane(resolved_session_key)
    global_lane = params_base.get("lane") or "main"
    workspace_resolution = resolve_run_workspace_dir(
        workspaceDir=params_base.get("workspaceDir"),
        sessionKey=resolved_session_key,
        agentId=resolved_agent_id,
        config=config_dict,
    )
    resolved_workspace_dir = workspace_resolution.get("workspaceDir") or ""
    canonical_workspace_dir = resolve_agent_workspace_dir(
        config_dict or {},
        workspace_resolution.get("agentId") or "",
    )
    is_canonical_workspace = (
        resolved_workspace_dir == canonical_workspace_dir
    )
    if workspace_resolution.get("usedFallback"):
        log.warning(
            "[workspace-fallback] run=%s session=%s sessionKey=%s agent=%s workspace=%s",
            params_base.get("runId"),
            resolved_session_id,
            resolved_session_key,
            workspace_resolution.get("agentId"),
            resolved_workspace_dir,
        )
    prepared = PreparedEmbeddedRunInput(
        run_params=RunEmbeddedAgentParamsWithSessionFile(
            dict(params_base, sessionFile=session_file)
        ),
        provider=provider,
        model_id=model_id,
        agent_dir=params_base.get("agentDir") or "",
        workspace_dir=resolved_workspace_dir,
        is_canonical_workspace=is_canonical_workspace,
        global_lane=global_lane,
        hook_context=None,
        fallback_configured=False,
        is_probe_session=bool(
            (resolved_session_id or "").startswith("probe-")
        ),
        resolved_session_key=resolved_session_key,
        resolved_tool_result_format="markdown",
        started_at_ms=started,
        lifecycle_generation=params_base.get(
            "lifecycleGeneration"
        )
        or get_agent_event_lifecycle_generation(),
    )
    prepared.workspace_resolution = workspace_resolution
    try:
        result = await run_prepared_embedded_loop(prepared)
        return result
    except Exception as err:
        _LOG.exception(
            "run_embedded_agent_internal failed"
        )
        return {
            "meta": {
                "durationMs": int(time.time() * 1000) - started,
                "agentMeta": {
                    "sessionId": session_id,
                    "provider": prepared.provider,
                    "model": prepared.model_id,
                },
                "error": {
                    "kind": "hook_block",
                    "message": str(err),
                    "fallbackSafe": False,
                },
            },
        }


__all__ = ["run_embedded_agent"]
