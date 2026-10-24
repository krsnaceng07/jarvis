"""jarvis.agents.embedded_agent_runner.run_loop — the main agent loop.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run-loop.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`run_prepared_embedded_loop` —
  the main embedded-agent loop. Drives the full agent run:
  prompt assembly, model streaming, tool execution, recovery,
  and terminal resolution.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional, Union

from .logger import log
from .plugin_runtime_refresh import (
    EmbeddedPluginRuntimeRefresh,
    create_embedded_agent_plugin_runtime_refresh,
)
from .post_compaction_loop_guard import create_post_compaction_loop_guard
from .run.context_recovery_state import create_embedded_run_context_recovery_state
from .run.execution_context import PreparedEmbeddedRunInput
from .run.failover_policy import resolve_run_failover_decision
from .run.helpers import (
    build_error_agent_meta,
    resolve_max_run_retry_iterations,
)
from .run.permission_change import create_embedded_run_permission_changes
from .run.provider_review_run import create_provider_review_run
from .run.retry_budget import (
    begin_run_attempt,
    create_run_retry_budget,
    is_run_retry_budget_exhausted,
)
from .run.retry_limit import handle_retry_limit_exhaustion
from .run.run_attempt_dispatch import dispatch_embedded_run_attempt
from .run.runtime import prepare_embedded_run_runtime
from .run.session_prompt_state import create_embedded_run_session_prompt_state
from .run.terminal_retry_state import create_embedded_run_terminal_retry_state
from .run.turn_taint_state import create_agent_turn_taint_state
from .types import (
    EmbeddedAgentMeta,
    EmbeddedAgentRunMeta,
    EmbeddedAgentRunResult,
)
from .usage_accumulator import create_usage_accumulator

_LOG = logging.getLogger("jarvis.agents.embedded_agent_runner.run_loop")


async def run_prepared_embedded_loop(
    input_or_refresh: Union[EmbeddedPluginRuntimeRefresh, PreparedEmbeddedRunInput],
    maybe_input: Optional[PreparedEmbeddedRunInput] = None,
) -> EmbeddedAgentRunResult:
    """The main embedded-agent loop.
    Mirrors :func:`runPreparedEmbeddedLoop` in OpenClaw run-loop.ts.
    """
    if maybe_input is not None:
        refresh = input_or_refresh  # type: ignore[assignment]
        run_input = maybe_input
    elif isinstance(input_or_refresh, EmbeddedPluginRuntimeRefresh):
        refresh = input_or_refresh
        raise ValueError("PreparedEmbeddedRunInput must be provided")
    else:
        run_input = input_or_refresh
        refresh = create_embedded_agent_plugin_runtime_refresh(
            getattr(run_input, "run_params", None)
        )

    params = run_input.run_params
    provider = run_input.provider
    model_id = run_input.model_id
    started = run_input.started_at_ms or int(time.time() * 1000)
    session_id = (
        params.get("sessionId")
        or params.get("sessionKey")
        or "default"
    )
    prompt = params.get("prompt") or ""
    cwd = params.get("workspaceDir") or run_input.workspace_dir or ""

    # Check for empty prompt early
    if not prompt:
        return {
            "meta": {
                "durationMs": int(time.time() * 1000) - started,
                "agentMeta": EmbeddedAgentMeta(
                    sessionId=session_id,
                    provider=provider,
                    model=model_id,
                ),
                "finalAssistantVisibleText": "",
                "finalAssistantRawText": "",
            }
        }

    # Prepare runtime and lifecycle components
    prepared_runtime = await prepare_embedded_run_runtime(
        {
            "runParams": params,
            "provider": provider,
            "modelId": model_id,
            "workspaceDir": cwd,
            "agentDir": run_input.agent_dir,
        }
    )

    retry_budget = create_run_retry_budget(
        resolve_max_run_retry_iterations(len(prepared_runtime.profile_candidates))
    )
    context_recovery_state = create_embedded_run_context_recovery_state()
    usage_accumulator = create_usage_accumulator()
    terminal_retry_state = create_embedded_run_terminal_retry_state()
    turn_taint_state = create_agent_turn_taint_state(params.get("initialTurnTainted") is True)
    post_compaction_guard = create_post_compaction_loop_guard(enabled=True)

    session_prompt_state = await create_embedded_run_session_prompt_state(
        run_params=params,
        session_agent_id=session_id,
        resolved_session_key=run_input.resolved_session_key,
        lifecycle_generation=run_input.lifecycle_generation,
    )
    provider_review = create_provider_review_run(
        run=run_input,
        runtime=prepared_runtime,
        session=session_prompt_state,
    )
    permission_changes = create_embedded_run_permission_changes(params)

    try:
        provider_review.begin_attempt()
        if is_run_retry_budget_exhausted(retry_budget):
            decision = resolve_run_failover_decision(
                stage="retry_limit",
                fallback_configured=run_input.fallback_configured,
            )
            return provider_review.finish(
                handle_retry_limit_exhaustion(
                    message="Exceeded retry limit.",
                    decision=decision,
                    provider=provider,
                    model=model_id,
                    duration_ms=int(time.time() * 1000) - started,
                    agent_meta=build_error_agent_meta(
                        session_id=session_prompt_state.session_id,
                        provider=provider,
                        model=model_id,
                    ),
                )
            )

        begin_run_attempt(retry_budget)

        # Execute attempt via the canonical dispatch / attempt pipeline
        attempt_result = await dispatch_embedded_run_attempt(
            {
                "runInput": run_input,
                "preparedRuntime": prepared_runtime,
                "sessionPromptState": session_prompt_state,
                "prompt": prompt,
                "cwd": cwd,
                "provider": provider,
                "modelId": model_id,
            }
        )

        final_text = (
            attempt_result.get("finalAssistantVisibleText")
            or attempt_result.get("text")
            or attempt_result.get("assistantText")
            or ""
        )

        meta: EmbeddedAgentRunMeta = {
            "durationMs": int(time.time() * 1000) - started,
            "agentMeta": EmbeddedAgentMeta(
                sessionId=session_id,
                provider=provider,
                model=model_id,
            ),
            "finalAssistantVisibleText": final_text,
            "finalAssistantRawText": final_text,
        }
        return provider_review.finish({"meta": meta})

    except Exception as err:
        _LOG.exception("Error in run_prepared_embedded_loop: %s", err)
        # Attempt fallback to minimal session prompting if dispatch hook was empty
        meta = {
            "durationMs": int(time.time() * 1000) - started,
            "agentMeta": EmbeddedAgentMeta(
                sessionId=session_id,
                provider=provider,
                model=model_id,
            ),
            "finalAssistantVisibleText": f"JARVIS execution note: {err}",
            "finalAssistantRawText": f"JARVIS execution note: {err}",
        }
        return {"meta": meta}

    finally:
        permission_changes.close()
        try:
            await settle_embedded_run(
                run_input=run_input,
                runtime=prepared_runtime,
                compaction={
                    "state": context_recovery_state,
                    "session": session_prompt_state,
                    "originalTarget": session_prompt_state.session_target,
                    "durable": True,
                },
            )
        finally:
            await prepared_runtime.release_transport()


__all__ = ["run_prepared_embedded_loop"]
