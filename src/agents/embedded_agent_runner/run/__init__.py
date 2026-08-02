"""jarvis.agents.embedded_agent_runner.run — run-stage helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/``.

This package holds the per-stage
helper files for the embedded-agent
loop (prompt assembly, stream,
tool execution, recovery,
terminal resolution, etc.).

Public surface (mirrors the OpenClaw
source):

- :func:`run_embedded_agent` —
  the public entrypoint (re-exported
  from :mod:`jarvis.agents.embedded_agent_runner.run_orchestrator`).
- :data:`RunEmbeddedAgentParams` —
  the public parameter shape.
- :data:`RunEmbeddedAgentInternalParams` —
  the orchestrator-internal
  parameter shape.
- :data:`RunEmbeddedAgentParamsWithSessionFile` —
  the internal shape with a
  resolved ``sessionFile``.
- :data:`PreparedEmbeddedRunInput` —
  the loop input shape.

Phase 7.1 — focused minimal port.
The full port of the ``run/``
subdir's 153 files lands in 7.6+.

The Python port mirrors the OpenClaw
folder structure exactly:
``src/agents/embedded_agent_runner/run/``
(OpenClaw uses
``embedded-agent-runner/run/``).

Note: the ``run/`` subdir is a
package (with ``__init__.py``).
The OpenClaw source's
``run.ts`` (a re-export at the
root) is mirrored by
:mod:`jarvis.agents.embedded_agent_runner.run_orchestrator`
+ the ``run_embedded_agent``
re-export at the package root
(via :mod:`jarvis.agents.embedded_agent_runner.__init__`).
"""
from __future__ import annotations

from ..run_orchestrator import run_embedded_agent
from .execution_context import PreparedEmbeddedRunInput
from .internal_params import (
    RunEmbeddedAgentInternalParams,
    RunEmbeddedAgentParamsWithSessionFile,
)
from .params import RunEmbeddedAgentParams


__all__ = [
    "PreparedEmbeddedRunInput",
    "RunEmbeddedAgentInternalParams",
    "RunEmbeddedAgentParams",
    "RunEmbeddedAgentParamsWithSessionFile",
    "run_embedded_agent",
]
