"""jarvis.agents.embedded_agent_runner.run_loop — the main agent loop.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run-loop.ts``.

Public surface (mirrors the OpenClaw
source):

- :func:`run_prepared_embedded_loop` —
  the main embedded-agent loop.
  Drives the full agent run:
  prompt assembly, model streaming,
  tool execution, recovery, +
  terminal resolution.

Phase 7.1 — focused minimal port.
The full implementation (with
compaction, attempt dispatch,
failover, retry, recovery, etc.)
lands in 7.2+ (when the
specialized sub-modules are
ported)."""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .run.execution_context import PreparedEmbeddedRunInput
from .types import (
    EmbeddedAgentMeta,
    EmbeddedAgentRunMeta,
    EmbeddedAgentRunResult,
)


_LOG = logging.getLogger(
    "jarvis.agents.embedded_agent_runner.run_loop"
)


async def run_prepared_embedded_loop(
    input: PreparedEmbeddedRunInput,
) -> EmbeddedAgentRunResult:
    """The main embedded-agent loop.
    Mirrors :func:`runPreparedEmbeddedLoop`
    (``run-loop.ts:55-635``).

    Phase 7.1 — focused minimal port:
    1. Resolve the session + tools
       via Layer 2's
       :func:`create_agent_session`
       (or the caller-provided
       session).
    2. Run the user prompt through
       the agent.
    3. Return an
       :class:`EmbeddedAgentRunResult`
       with the final assistant
       text + meta.

    The full implementation (with
    compaction, failover, retry,
    recovery, hooks, etc.) lands in
    7.2+.
    """
    started = input.started_at_ms or int(time.time() * 1000)
    run_params = input.run_params
    provider = input.provider
    model_id = input.model_id
    session_id = (
        run_params.get("sessionId")
        or run_params.get("sessionKey")
        or "default"
    )
    cwd = (
        run_params.get("workspaceDir")
        or input.workspace_dir
        or ""
    )
    prompt = run_params.get("prompt") or ""

    _LOG.info(
        f"run_prepared_embedded_loop: "
        f"sessionId={session_id} "
        f"provider={provider} modelId={model_id} "
        f"cwd={cwd} promptLen={len(prompt)}"
    )

    # Build the final response.
    # Phase 7.1 — STUB: the actual
    # agent run lands in 7.2+ (when
    # the Layer 2 ``Agent`` class
    # is integrated with the
    # full Layer 3 loop).
    final_text = _run_minimal_agent_loop(
        session_id=session_id,
        cwd=cwd,
        prompt=prompt,
        provider=provider,
        model_id=model_id,
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
    return {"meta": meta}


def _run_minimal_agent_loop(
    session_id: str,
    cwd: str,
    prompt: str,
    provider: str,
    model_id: str,
) -> str:
    """The minimal agent loop for
    Phase 7.1. Returns a basic
    final-text response (the full
    loop with model streaming,
    tool execution, etc. lands in
    7.2+).

    The Phase 7.1 stub returns a
    placeholder response — the
    goal is to wire the
    orchestrator + loop entry
    point so callers can integrate.
    """
    if not prompt:
        return ""
    return (
        f"[Phase 7.1 stub] session={session_id} "
        f"provider={provider} model={model_id} "
        f"cwd={cwd} prompt={prompt[:60]!r}"
    )


__all__ = ["run_prepared_embedded_loop"]
