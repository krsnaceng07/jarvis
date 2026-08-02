"""jarvis.agents.embedded_agent_runner.types — public types for the runner.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/types.ts``.

Shared metadata + result types for
embedded-agent runner surfaces.

Public surface (mirrors the OpenClaw
source):

- :data:`BlockReplyFlushContext`
- :data:`EmbeddedAgentMeta`
- :data:`TraceAttempt`
- :data:`ToolSummaryTrace`
- :data:`EmbeddedRunLivenessState`
- :data:`EmbeddedRunFailureSignal`
- :data:`EmbeddedAgentRunMeta`
- :data:`EmbeddedAgentRunResult`
- :data:`EmbeddedAgentCompactResult`
- :data:`EmbeddedFullAccessBlockedReason`
- :data:`EmbeddedSandboxInfo`
- :data:`EmbeddedSandboxElevated`

Phase 7.0 — public types for
Layer 3. Mirrors the OpenClaw
source 1:1 (snake_case for Python).

Adaptations
-----------
- The OpenClaw source's
  ``import type`` declarations
  reference types from
  ``../../config/sessions/types.js``,
  ``../embedded-agent-messaging.types.js``,
  etc. The Python port uses plain
  :class:`dict` for all the
  referenced types (the
  ``TypedDict`` shapes land in
  Phase 7.1+ when the
  ``embedded-agent-messaging``,
  ``mcp-ui-resource``, and
  ``model-fallback`` modules
  are ported).
- The OpenClaw source's
  ``Usage`` + ``ContextUsage`` types
  come from
  ``../usage.ts``. The Python
  port's :class:`ContextUsage`
  is a TypedDict in
  :mod:`jarvis.agents.sessions.extensions.types`
  (Phase 6.9c).
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict, Union


#: A block-reply flush context. Mirrors
#: :class:`BlockReplyFlushContext`
#: (``types.ts:21-35``).
BlockReplyFlushContext = dict


#: An agent-meta block. Mirrors
#: :class:`EmbeddedAgentMeta`
#: (``types.ts:37-85``). The
#: ``Usage`` + ``ContextUsage``
#: shapes are plain ``dict`` in the
#: Python port (the typed shapes
#: land in 7.1+).
class EmbeddedAgentMeta(TypedDict, total=False):
    sessionId: str
    sessionFile: Optional[str]
    provider: str
    model: str
    contextTokens: Optional[int]
    agentHarnessId: Optional[str]
    fallbackAttempts: Optional[list]
    cliSessionBinding: Optional[dict]
    clearCliSessionBinding: Optional[bool]
    compactionCount: Optional[int]
    compactionTokensAfter: Optional[int]
    promptTokens: Optional[int]
    usage: Optional[dict]
    lastCallUsage: Optional[dict]
    contextBudgetStatus: Optional[dict]


#: A trace attempt. Mirrors
#: :class:`TraceAttempt`
#: (``types.ts:87-104``).
class TraceAttempt(TypedDict, total=False):
    provider: str
    model: str
    result: str  # "success" | "timeout" | ...
    reason: Optional[str]
    stage: Optional[str]  # "prompt" | "assistant"
    elapsedMs: Optional[int]
    status: Optional[int]


#: A tool-summary trace. Mirrors
#: :class:`ToolSummaryTrace`
#: (``types.ts:129-134``).
class ToolSummaryTrace(TypedDict, total=False):
    calls: int
    tools: list[str]
    failures: Optional[int]
    totalToolTimeMs: Optional[int]


#: The liveness state of an
#: embedded run. Mirrors
#: :class:`EmbeddedRunLivenessState`
#: (``types.ts:149``).
EmbeddedRunLivenessState = str  # "working" | "paused" | "blocked" | "abandoned"


#: A failure-signal block. Mirrors
#: :class:`EmbeddedRunFailureSignal`
#: (``types.ts:151-158``).
class EmbeddedRunFailureSignal(TypedDict, total=False):
    kind: str  # "execution_denied"
    source: str  # "tool"
    toolName: Optional[str]
    code: str  # "SYSTEM_RUN_DENIED" | "INVALID_REQUEST"
    message: str
    fatalForCron: bool


#: A run-meta block. Mirrors
#: :class:`EmbeddedAgentRunMeta`
#: (``types.ts:160-205``).
class EmbeddedAgentRunMeta(TypedDict, total=False):
    durationMs: int
    agentMeta: Optional[EmbeddedAgentMeta]
    aborted: Optional[bool]
    systemPromptReport: Optional[dict]
    finalPromptText: Optional[str]
    finalAssistantVisibleText: Optional[str]
    finalAssistantRawText: Optional[str]
    replayInvalid: Optional[bool]
    livenessState: Optional[EmbeddedRunLivenessState]
    timeoutPhase: Optional[str]
    providerStarted: Optional[bool]
    agentHarnessResultClassification: Optional[str]
    terminalReplyKind: Optional[str]
    yielded: Optional[bool]
    error: Optional[dict]
    failureSignal: Optional[EmbeddedRunFailureSignal]
    stopReason: Optional[str]
    pendingToolCalls: Optional[list[dict]]
    executionTrace: Optional[dict]
    requestShaping: Optional[dict]
    promptSegments: Optional[list[dict]]
    toolSummary: Optional[ToolSummaryTrace]
    completion: Optional[dict]
    contextManagement: Optional[dict]


#: A run result. Mirrors
#: :class:`EmbeddedAgentRunResult`
#: (``types.ts:207-245``).
class EmbeddedAgentRunResult(TypedDict, total=False):
    latestMcpAppChannelView: Optional[dict]
    payloads: Optional[list[dict]]
    meta: EmbeddedAgentRunMeta
    diagnosticTrace: Optional[dict]
    didSendViaMessagingTool: Optional[bool]
    didDeliverSourceReplyViaMessageTool: Optional[bool]
    didSendDeterministicApprovalPrompt: Optional[bool]
    messagingToolSentTexts: Optional[list[str]]
    messagingToolSentMediaUrls: Optional[list[str]]
    messagingToolSentTargets: Optional[list[dict]]
    messagingToolSourceReplyPayloads: Optional[list[dict]]
    acceptedSessionSpawns: Optional[list[dict]]
    heartbeatToolResponse: Optional[dict]
    successfulCronAdds: Optional[int]


#: A compact result. Mirrors
#: :class:`EmbeddedAgentCompactResult`
#: (``types.ts:247-267``).
class EmbeddedAgentCompactResult(TypedDict, total=False):
    ok: bool
    compacted: bool
    reason: Optional[str]
    failure: Optional[dict]
    result: Optional[dict]


#: A full-access-blocked reason. Mirrors
#: :class:`EmbeddedFullAccessBlockedReason`
#: (``types.ts:269``).
EmbeddedFullAccessBlockedReason = str  # "sandbox" | "host-policy" | "channel" | "runtime"


#: A sandbox info block. Mirrors
#: :class:`EmbeddedSandboxInfo`
#: (``types.ts:271-284``).
class EmbeddedSandboxElevated(TypedDict, total=False):
    allowed: bool
    defaultLevel: str  # "on" | "off" | "ask" | "full"
    fullAccessAvailable: bool
    fullAccessBlockedReason: Optional[EmbeddedFullAccessBlockedReason]


class EmbeddedSandboxInfo(TypedDict, total=False):
    enabled: bool
    workspaceDir: Optional[str]
    containerWorkspaceDir: Optional[str]
    workspaceAccess: Optional[str]  # "none" | "ro" | "rw"
    agentWorkspaceMount: Optional[str]
    browserBridgeUrl: Optional[str]
    hostBrowserAllowed: Optional[bool]
    elevated: Optional[EmbeddedSandboxElevated]


__all__ = [
    "BlockReplyFlushContext",
    "EmbeddedAgentCompactResult",
    "EmbeddedAgentMeta",
    "EmbeddedAgentRunMeta",
    "EmbeddedAgentRunResult",
    "EmbeddedFullAccessBlockedReason",
    "EmbeddedRunFailureSignal",
    "EmbeddedRunLivenessState",
    "EmbeddedSandboxElevated",
    "EmbeddedSandboxInfo",
    "ToolSummaryTrace",
    "TraceAttempt",
]
