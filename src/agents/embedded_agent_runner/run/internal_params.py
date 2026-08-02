"""jarvis.agents.embedded_agent_runner.run.internal_params — orchestrator-internal params.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/internal-params.ts``.

Public surface (mirrors the OpenClaw
source):

- :data:`RunEmbeddedAgentInternalParams` —
  the internal parameter shape
  (extends :data:`RunEmbeddedAgentParams`
  with orchestrator-injected
  fields).
- :data:`RunEmbeddedAgentParamsWithSessionFile` —
  the internal parameter shape
  with a resolved ``sessionFile``.

Phase 7.1 — focused minimal port.
The OpenClaw source's
``AgentExecutionAuthBinding`` +
``SystemAgentToolOptions`` types
land in 7.2+ (when the
specialized sub-modules are
ported)."""
from __future__ import annotations

from typing import Any, Optional

from .params import RunEmbeddedAgentParams


#: The orchestrator-internal
#: parameter shape. Mirrors
#: :class:`RunEmbeddedAgentInternalParams`
#: (``internal-params.ts:5-10``).
class RunEmbeddedAgentInternalParams(RunEmbeddedAgentParams, total=False):
    #: Optional auth binding callback
    #: (lands in 7.2+).
    onSuccessfulAuthBinding: Optional[Any]
    #: Auth profile state mode.
    authProfileStateMode: Optional[str]
    #: Ring-zero tool override
    #: (supplied only by the
    #: OpenClaw orchestrator).
    systemAgentTool: Optional[Any]


#: The internal parameter shape
#: with a resolved session file.
#: Mirrors
#: :class:`RunEmbeddedAgentParamsWithSessionFile`
#: (``internal-params.ts:12-14``).
class RunEmbeddedAgentParamsWithSessionFile(
    RunEmbeddedAgentInternalParams, total=False
):
    sessionFile: str


__all__ = [
    "RunEmbeddedAgentInternalParams",
    "RunEmbeddedAgentParamsWithSessionFile",
]
