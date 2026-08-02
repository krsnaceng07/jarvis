"""jarvis.agents.embedded_agent_runner.run — public entrypoint.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run.ts``.

Public surface (mirrors the OpenClaw
source):

- :func:`run_embedded_agent` —
  the public embedded-agent run
  entrypoint.

Phase 7.0 — STUB. The full
implementation lands in 7.1+
(when the orchestrator + run loop
are ported)."""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING


if TYPE_CHECKING:
    from .types import EmbeddedAgentRunResult


_LOG = logging.getLogger(
    "jarvis.agents.embedded_agent_runner.run"
)


async def run_embedded_agent(
    params: Any,
) -> "EmbeddedAgentRunResult":
    """Public embedded-agent run
    entrypoint. Mirrors
    :func:`runEmbeddedAgent`
    (``run-orchestrator.ts:59-80``).

    Phase 7.0 — STUB. The full
    implementation lands in 7.1+
    (when the orchestrator is
    ported)."""
    _LOG.debug(
        "run_embedded_agent stub called; "
        "full implementation lands in 7.1+"
    )
    raise NotImplementedError(
        "run_embedded_agent is a stub in 7.0; "
        "the full implementation lands in 7.1+"
    )


__all__ = ["run_embedded_agent"]
