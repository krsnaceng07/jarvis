"""jarvis.agents.embedded_agent_runner.run_execution — re-export.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run-execution.ts``.

The OpenClaw source re-exports
:func:`runPreparedEmbeddedLoop`
from :mod:`./run-loop.js` as
:func:`executePreparedEmbeddedRun`.

Phase 7.1 — re-export of
:func:`run_prepared_embedded_loop`
from :mod:`.run_loop`."""
from __future__ import annotations

from .run_loop import run_prepared_embedded_loop


#: Re-export. Mirrors
#: :func:`executePreparedEmbeddedRun`
#: (``run-execution.ts:6-9``).
execute_prepared_embedded_run = run_prepared_embedded_loop


__all__ = ["execute_prepared_embedded_run"]

