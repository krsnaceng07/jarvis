"""jarvis.agents.embedded_agent_runner.run.params — shared parameter types.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/params.ts``.

Public surface (mirrors the OpenClaw
source):

- :data:`RunEmbeddedAgentParams` —
  the public parameter shape for
  :func:`run_embedded_agent`.

Phase 7.1 — focused minimal port.
The OpenClaw source has ~330 lines
of TypedDict definitions (the full
parameter shape with all
specialized fields). The Python
port ships a focused minimal
subset that the orchestrator +
loop consume; the full shape
expands in 7.2+ (when the
specialized sub-modules are
ported)."""
from __future__ import annotations

from typing import Any, Optional, TypedDict


#: The public parameter shape for
#: :func:`run_embedded_agent`.
#: Mirrors :class:`RunEmbeddedAgentParams`
#: (``params.ts:1-330``). The
#: Python port ships a focused
#: minimal subset; the full
#: shape lands in 7.2+.
class RunEmbeddedAgentParams(TypedDict, total=False):
    # ---- Identity / session ----
    runId: Optional[str]
    sessionId: Optional[str]
    sessionKey: Optional[str]
    sessionFile: Optional[str]
    agentId: Optional[str]
    config: Optional[Any]  # OpenClawConfig
    agentDir: Optional[str]
    workspaceDir: Optional[str]
    # ---- Prompt ----
    prompt: Optional[str]
    images: Optional[list]  # list[ImageContent]
    # ---- Model ----
    provider: Optional[str]
    model: Optional[str]
    lifecycleGeneration: Optional[int]
    # ---- Run options ----
    trigger: Optional[str]  # "user" | "cron" | etc.
    runId: Optional[str]
    lane: Optional[str]  # global lane
    # ---- Hooks ----
    onExecutionStarted: Optional[Any]
    replyOperation: Optional[Any]
    # ---- Misc ----
    allowGatewaySubagentBinding: Optional[bool]
    modelFallbacksOverride: Optional[Any]
    sessionTarget: Optional[Any]
    skillWorkshopProposalOnly: Optional[bool]
    skillWorkshopProposalMutationBudget: Optional[Any]


__all__ = ["RunEmbeddedAgentParams"]
