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
from typing import Any, Optional

from .lanes import resolve_session_lane
from .logger import log
from .run.execution_context import PreparedEmbeddedRunInput
from .run.internal_params import RunEmbeddedAgentInternalParams
from .run_loop import run_prepared_embedded_loop
from .types import EmbeddedAgentRunResult


_LOG = logging.getLogger(
    "jarvis.agents.embedded_agent_runner.run_orchestrator"
)


def run_embedded_agent(
    params_input: Any,
) -> "EmbeddedAgentRunResult":
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
    # Phase 7.1 — synchronous wrapper
    # around the async internal
    # function. The OpenClaw source
    # uses
    # ``withAgentRunLifecycleGeneration``
    # to capture the lifecycle
    # generation; the Python port
    # uses a no-op stub.
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        # Already in an async context
        # — return the coroutine for
        # the caller to await.
        return _run_embedded_agent_internal_async(internal)
    else:
        # Sync context — run via
        # ``asyncio.run``.
        return asyncio.run(
            _run_embedded_agent_internal_async(internal)
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
    params_base = dict(params_input)
    # Resolve the session key.
    session_key = (
        params_base.get("sessionKey")
        or params_base.get("sessionId")
        or "default"
    )
    session_id = params_base.get("sessionId") or session_key
    # Resolve the lanes.
    session_lane = resolve_session_lane(session_key)
    global_lane = params_base.get("lane") or "main"
    # Build the prepared input.
    prepared = PreparedEmbeddedRunInput(
        run_params=dict(params_base, sessionFile=""),
        provider=params_base.get("provider") or "default",
        model_id=params_base.get("model") or "default",
        agent_dir=params_base.get("agentDir") or "",
        workspace_dir=params_base.get("workspaceDir") or "",
        is_canonical_workspace=False,
        global_lane=global_lane,
        hook_context=None,
        fallback_configured=False,
        is_probe_session=bool(
            (session_id or "").startswith("probe-")
        ),
        resolved_session_key=session_key,
        resolved_tool_result_format="markdown",
        started_at_ms=started,
        lifecycle_generation=params_base.get(
            "lifecycleGeneration"
        )
        or 0,
    )
    # Invoke the main loop.
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
