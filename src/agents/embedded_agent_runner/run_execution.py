"""jarvis.agents.embedded_agent_runner.run_execution — re-export stub.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run-execution.ts``.

The OpenClaw source re-exports
:func:`runPreparedEmbeddedLoop`
from :mod:`./run-loop.js` as
:func:`executePreparedEmbeddedRun`.

Phase 7.0 — STUB. The full
:func:`run_prepared_embedded_loop`
function lands in 7.1+ (when
:mod:`run_loop` is ported)."""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING


if TYPE_CHECKING:
    from .types import EmbeddedAgentRunResult


_LOG = logging.getLogger(
    "jarvis.agents.embedded_agent_runner.run_execution"
)


async def execute_prepared_embedded_run(
    input: Any,
) -> "EmbeddedAgentRunResult":
    """Run one fully prepared
    embedded-agent request. Mirrors
    :func:`executePreparedEmbeddedRun`
    (``run-execution.ts:6-9``).

    Phase 7.0 — STUB. The full
    implementation lands in 7.1+
    (when :mod:`run_loop` is ported)."""
    _LOG.debug(
        "execute_prepared_embedded_run stub called; "
        "full implementation lands in 7.1+"
    )
    raise NotImplementedError(
        "execute_prepared_embedded_run is a stub in 7.0; "
        "the full implementation lands in 7.1+"
    )


__all__ = ["execute_prepared_embedded_run"]
