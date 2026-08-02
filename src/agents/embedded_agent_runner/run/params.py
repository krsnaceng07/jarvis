"""jarvis.agents.embedded_agent_runner.run.params — embedded-run params TypedDicts.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/params.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`EmbeddedRunTrigger` — Literal type for the run trigger.
- :data:`CurrentInboundPromptContext` — TypedDict for the current
  inbound prompt context (text + resumable text + joiner + goal
  contexts).
- :data:`RunEmbeddedAgentParams` — TypedDict for the embedded-run
  params (the main entry params for :func:`run_embedded_agent`).
- :data:`RunEmbeddedAgentInternalParams` — TypedDict for the
  internal params (extends RunEmbeddedAgentParams with internal
  fields used by the run-attempt dispatch).

Phase 7.6a — focused minimal port.

The OpenClaw source is 400+ lines of TypedDict fields plus
re-exports. The Python port keeps the same shape as a
TypedDict subclass so callers can build the params dict the
same way the OpenClaw source does, but uses dict-style typing
(rather than full mypy TypedDict validation) to keep the
implementation focused.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union


#: Re-export the ClientToolDefinition type. Mirrors
#: ``export type { ClientToolDefinition } from "../../command/shared-types.js"``
#: (``params.ts:50``).
ClientToolDefinition = Dict[str, Any]


#: Embedded-run trigger values. Mirrors
#: :data:`EmbeddedRunTrigger`` (``params.ts:52``).
EmbeddedRunTrigger = str  # "cron" | "heartbeat" | "manual" | "memory" | "overflow" | "user"


#: Current inbound prompt context. Mirrors
#: :class:`CurrentInboundPromptContext`` (``params.ts:61-67``).
CurrentInboundPromptContext = Dict[str, Any]


#: Run-embedded-agent params. Mirrors
#: :class:`RunEmbeddedAgentParams`` (``params.ts:69-...``).
RunEmbeddedAgentParams = Dict[str, Any]


#: Internal run-embedded-agent params. Mirrors
#: :class:`RunEmbeddedAgentInternalParams``. The Python port
#: exposes the same fields as a dict-typed alias.
RunEmbeddedAgentInternalParams = Dict[str, Any]


#: Reasoning-stream payload shape (mirrors the OpenClaw source
#: ``ReasoningStreamPayload``).
ReasoningStreamPayload = Dict[str, Any]


#: Auth-profile failure policy shape.
AuthProfileFailurePolicy = Dict[str, Any]


#: A small set of well-known field names that callers frequently
#: pass. Useful for the focused minimal port tests.
_RUN_PARAMS_KNOWN_FIELDS: List[str] = [
    "sessionId",
    "sessionKey",
    "sessionTarget",
    "lifecycleGeneration",
    "promptCacheKey",
    "sandboxSessionKey",
    "agentId",
    "messageChannel",
    "messageProvider",
    "clientCaps",
    "toolBindings",
    "chatType",
    "agentAccountId",
    "trigger",
    "jobId",
    "memoryFlushWritePath",
    "messageTo",
    "messageThreadId",
    "groupId",
    "groupChannel",
    "groupSpace",
    "memberRoleIds",
    "messageActionTurnCapability",
    "spawnedBy",
    "isCanonicalWorkspace",
    "senderId",
    "senderName",
    "senderUsername",
    "senderE164",
    "senderIsOwner",
    "approvalReviewerDeviceId",
    "currentChannelId",
    "chatId",
    "channelContext",
    "currentMessagingTarget",
    "currentThreadTs",
    "currentMessageId",
    "currentInboundAudio",
    "replyToMode",
    "hasRepliedRef",
    "requireExplicitMessageTarget",
    "disableMessageTool",
    "swarmCollector",
    "swarmOutputSchema",
    "forceRestartSafeTools",
    "modelRun",
    "disableTrajectory",
    "skillWorkshopProposalOnly",
    "skillWorkshopOrigin",
    "skillWorkshopProposalMutationBudget",
    "skillWorkshopProposalEnv",
    "skillWorkshopCompletionLatch",
    "isProbeSession",
    "isHeartbeat",
    "abortSignal",
    "fallbackConfigured",
    "preResolvedLane",
    "preResolvedToolResultFormat",
    "lifecycleController",
    "suspendForFailure",
]


def get_run_param_keys() -> List[str]:
    """Return the list of known run-param field names.

    Mirrors the OpenClaw source's expected set of fields on
    :class:`RunEmbeddedAgentParams`.
    """
    return list(_RUN_PARAMS_KNOWN_FIELDS)


__all__ = [
    "AuthProfileFailurePolicy",
    "ClientToolDefinition",
    "CurrentInboundPromptContext",
    "EmbeddedRunTrigger",
    "ReasoningStreamPayload",
    "RunEmbeddedAgentInternalParams",
    "RunEmbeddedAgentParams",
    "get_run_param_keys",
]
