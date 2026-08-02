"""jarvis.agents.embedded_agent_runner.compact_types — compaction parameter types.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/compact.types.ts``.

Public surface (mirrors the OpenClaw
source):

- :data:`CompactEmbeddedAgentSessionParams` —
  the public parameter shape for
  direct embedded session
  compaction.
- :data:`CompactEmbeddedAgentSessionRuntimeParams` —
  the runtime parameter shape
  (extends the public one with the
  deprecated ``sessionFile``).
- :data:`CompactionMessageMetrics` —
  the per-message compaction
  metrics.

Phase 7.2a — focused minimal port.
The OpenClaw source's full
``CompactEmbeddedAgentSessionParams``
has ~120 fields; the Python port
ships the focused minimal subset
that the helpers consume (the
full shape expands in 7.2b+
when the specialized sub-modules
are ported)."""
from __future__ import annotations

from typing import Any, Optional, TypedDict


#: The public parameter shape for
#: direct embedded session
#: compaction. Mirrors
#: :class:`CompactEmbeddedAgentSessionParams`
#: (``compact.types.ts:16-120``).
#: The Python port ships a focused
#: minimal subset; the full
#: shape lands in 7.2b+.
class CompactEmbeddedAgentSessionParams(TypedDict, total=False):
    # ---- Identity / session ----
    sessionId: Optional[str]
    runId: Optional[str]
    sessionKey: Optional[str]
    sessionTarget: Optional[Any]
    agentId: Optional[str]
    sandboxSessionKey: Optional[str]
    # ---- Channel / sender ----
    messageChannel: Optional[str]
    messageProvider: Optional[str]
    chatType: Optional[str]
    currentChannelId: Optional[str]
    currentThreadTs: Optional[str]
    currentMessageId: Optional[Any]
    senderId: Optional[str]
    senderName: Optional[str]
    senderUsername: Optional[str]
    senderE164: Optional[str]
    # ---- Auth / credentials ----
    authProfileId: Optional[str]
    resolvedApiKey: Optional[str]
    # ---- Group / context ----
    groupId: Optional[str]
    groupChannel: Optional[str]
    groupSpace: Optional[str]
    spawnedBy: Optional[str]
    # ---- Storage / workspace ----
    sessionFile: Optional[str]
    workspaceDir: Optional[str]
    cwd: Optional[str]
    agentDir: Optional[str]
    config: Optional[Any]
    skillsSnapshot: Optional[Any]
    # ---- Model ----
    provider: Optional[str]
    model: Optional[str]
    runtimeModel: Optional[Any]
    modelFallbacksOverride: Optional[Any]
    # ---- Compaction control ----
    trigger: Optional[str]  # "budget" | "overflow" | "manual"
    force: Optional[bool]
    forcePreflight: Optional[bool]
    preflightRequired: Optional[bool]
    preflightCompactionTrigger: Optional[str]
    deferOwningContextEngineCompaction: Optional[bool]
    diagId: Optional[str]
    attempt: Optional[int]
    maxAttempts: Optional[int]
    lane: Optional[str]
    customInstructions: Optional[str]
    tokenBudget: Optional[int]
    extraSystemPrompt: Optional[str]
    # ---- Lifecycle ----
    sourceReplyDeliveryMode: Optional[str]
    ownerNumbers: Optional[Any]
    abortSignal: Optional[Any]
    onCompactionHookMessages: Optional[Any]
    allowGatewaySubagentBinding: Optional[bool]
    oneShotCliRun: Optional[bool]
    thinkLevel: Optional[str]
    reasoningLevel: Optional[str]


#: The runtime parameter shape
#: (extends the public shape with
#: the deprecated ``sessionFile``).
#: Mirrors
#: :class:`CompactEmbeddedAgentSessionRuntimeParams`
#: (``compact.types.ts:122-128``).
class CompactEmbeddedAgentSessionRuntimeParams(
    CompactEmbeddedAgentSessionParams, total=False
):
    sessionFile: Optional[str]


#: The per-message compaction
#: metrics. Mirrors
#: :class:`CompactionMessageMetrics`
#: (``compact.types.ts:130-136``).
class CompactionMessageMetrics(TypedDict, total=False):
    messages: int
    historyTextChars: int
    toolResultChars: int
    estTokens: Optional[int]
    contributors: Optional[list]


__all__ = [
    "CompactEmbeddedAgentSessionParams",
    "CompactEmbeddedAgentSessionRuntimeParams",
    "CompactionMessageMetrics",
]
