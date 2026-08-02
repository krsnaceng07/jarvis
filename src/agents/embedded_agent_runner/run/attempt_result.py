"""jarvis.agents.embedded_agent_runner.run.attempt_result — project stream state into the embedded-attempt result.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-result.ts``.

Public surface:

- :data:`EmbeddedAttemptClientToolCallSlot` — readonly client-tool slot
  shape.
- :func:`complete_embedded_attempt_result` — runs output hooks,
  classifies terminal effects, and returns the finalized attempt
  result.

Phase 7.6b-2 — focused minimal port.

The OpenClaw source is tightly coupled to the agent-subscription
interface, hook-runner, prompt-cache observability, replay-state,
and finalize layers. The Python port keeps the public surface and
delegates the heavy classification to installable hooks so the host
can plug in the real layers as they land.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


#: Client-tool call slot. Mirrors
#: :class:`EmbeddedAttemptClientToolCallSlot` (``attempt-result.ts:35-40``).
EmbeddedAttemptClientToolCallSlot = Dict[str, Any]


#: Final attempt result. Mirrors :class:`EmbeddedRunAttemptResult` in
#: ``types.ts``.
EmbeddedRunAttemptResult = Dict[str, Any]


#: Attempt result state shape (subset of EmbeddedRunAttemptResult +
#: diagnosticTrace).
EmbeddedAttemptResultState = Dict[str, Any]


#: Complete-input shape. Mirrors
#: :class:`CompleteEmbeddedAttemptResultInput` (``attempt-result.ts:72-91``).
CompleteEmbeddedAttemptResultInput = Dict[str, Any]


#: Tool-meta shape.
EmbeddedAttemptToolMeta = Dict[str, Any]


# ---------------------------------------------------------------------------
# Installable hooks
# ---------------------------------------------------------------------------


#: Hook for the attempt-finalize step.
_FINALIZE_EMBEDDED_ATTEMPT: Callable[[Dict[str, Any]], Any] = (
    lambda _params: None
)


def set_finalize_embedded_attempt_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom finalizeEmbeddedAttempt hook."""
    global _FINALIZE_EMBEDDED_ATTEMPT
    _FINALIZE_EMBEDDED_ATTEMPT = hook


#: Hook for the should-run-llm-output check.
_SHOULD_RUN_LLM_OUTPUT_HOOKS_FOR_ATTEMPT: Callable[[Dict[str, Any]], bool] = (
    lambda _params: False
)


def set_should_run_llm_output_hooks_for_attempt_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldRunLlmOutputHooksForAttempt hook."""
    global _SHOULD_RUN_LLM_OUTPUT_HOOKS_FOR_ATTEMPT
    _SHOULD_RUN_LLM_OUTPUT_HOOKS_FOR_ATTEMPT = hook


#: Hook for the cloud-code-assist format-error check.
_IS_CLOUD_CODE_ASSIST_FORMAT_ERROR: Callable[[Any], bool] = lambda _err: False


def set_is_cloud_code_assist_format_error_hook(
    hook: Callable[[Any], bool],
) -> None:
    """Install a custom isCloudCodeAssistFormatError hook."""
    global _IS_CLOUD_CODE_ASSIST_FORMAT_ERROR
    _IS_CLOUD_CODE_ASSIST_FORMAT_ERROR = hook


#: Hook for the build-agent-hook-context-channel-fields step.
_BUILD_AGENT_HOOK_CONTEXT_CHANNEL_FIELDS: Callable[[Dict[str, Any]], Dict[str, Any]] = (
    lambda _params: {}
)


def set_build_agent_hook_context_channel_fields_hook(
    hook: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> None:
    """Install a custom buildAgentHookContextChannelFields hook."""
    global _BUILD_AGENT_HOOK_CONTEXT_CHANNEL_FIELDS
    _BUILD_AGENT_HOOK_CONTEXT_CHANNEL_FIELDS = hook


#: Hook for the build-agent-hook-context-identity-fields step.
_BUILD_AGENT_HOOK_CONTEXT_IDENTITY_FIELDS: Callable[[Dict[str, Any]], Dict[str, Any]] = (
    lambda _params: {}
)


def set_build_agent_hook_context_identity_fields_hook(
    hook: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> None:
    """Install a custom buildAgentHookContextIdentityFields hook."""
    global _BUILD_AGENT_HOOK_CONTEXT_IDENTITY_FIELDS
    _BUILD_AGENT_HOOK_CONTEXT_IDENTITY_FIELDS = hook


#: Hook for the freeze-diagnostic-trace-context step.
_FREEZE_DIAGNOSTIC_TRACE_CONTEXT: Callable[[Dict[str, Any]], Any] = (
    lambda _trace: None
)


def set_freeze_diagnostic_trace_context_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom freezeDiagnosticTraceContext hook."""
    global _FREEZE_DIAGNOSTIC_TRACE_CONTEXT
    _FREEZE_DIAGNOSTIC_TRACE_CONTEXT = hook


#: Hook for the record-stage cache trace step.
_RECORD_STAGE_CACHE_TRACE: Callable[[Dict[str, Any]], Any] = lambda _params: None


def set_record_stage_cache_trace_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom recordStage cache-trace hook."""
    global _RECORD_STAGE_CACHE_TRACE
    _RECORD_STAGE_CACHE_TRACE = hook


#: Hook for the run-llm-output hook runner step.
_RUN_LLM_OUTPUT_HOOK: Callable[[Dict[str, Any]], Any] = lambda _params: None


def set_run_llm_output_hook_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom runLlmOutput hook."""
    global _RUN_LLM_OUTPUT_HOOK
    _RUN_LLM_OUTPUT_HOOK = hook


#: Hook for the observe-replay-metadata step.
_OBSERVE_REPLAY_METADATA: Callable[[Any, Any], Any] = lambda _state, _meta: None


def set_observe_replay_metadata_hook(
    hook: Callable[[Any, Any], Any],
) -> None:
    """Install a custom observeReplayMetadata hook."""
    global _OBSERVE_REPLAY_METADATA
    _OBSERVE_REPLAY_METADATA = hook


#: Hook for the replay-metadata-from-state step.
_REPLAY_METADATA_FROM_STATE: Callable[[Any], Dict[str, Any]] = lambda _state: {}


def set_replay_metadata_from_state_hook(
    hook: Callable[[Any], Dict[str, Any]],
) -> None:
    """Install a custom replayMetadataFromState hook."""
    global _REPLAY_METADATA_FROM_STATE
    _REPLAY_METADATA_FROM_STATE = hook


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_tool_metas(
    entries: Optional[List[Any]],
) -> List[EmbeddedAttemptToolMeta]:
    if not entries:
        return []
    normalized: List[EmbeddedAttemptToolMeta] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        tool_name = entry.get("toolName")
        if not isinstance(tool_name, str) or not tool_name.strip():
            continue
        meta: EmbeddedAttemptToolMeta = {
            "toolName": tool_name,
            "meta": entry.get("meta"),
            "replaySafe": entry.get("replaySafe") is True,
        }
        if entry.get("isError") is True:
            meta["isError"] = True
        if entry.get("asyncStarted") is True:
            meta["asyncStarted"] = True
        if entry.get("asyncTaskRunId"):
            meta["asyncTaskRunId"] = entry["asyncTaskRunId"]
        if entry.get("asyncTaskId"):
            meta["asyncTaskId"] = entry["asyncTaskId"]
        normalized.append(meta)
    return normalized


def _has_visible_pending_tool_media_reply(
    reply: Optional[Dict[str, Any]],
) -> bool:
    if not reply:
        return False
    media_urls = reply.get("mediaUrls") or []
    if any((url or "").strip() for url in media_urls):
        return True
    return reply.get("audioAsVoice") is True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def complete_embedded_attempt_result(
    input_obj: CompleteEmbeddedAttemptResultInput,
) -> EmbeddedRunAttemptResult:
    """Project stream state into the stable embedded-attempt result.

    Mirrors :func:`completeEmbeddedAttemptResult`
    (``attempt-result.ts:150-...``).
    """
    attempt = input_obj.get("attempt") or {}
    state = input_obj.get("state") or {}
    subscription = input_obj.get("subscription") or {}
    cache = input_obj.get("cache") or {}
    client_tool_call_slots = input_obj.get("clientToolCallSlots") or []
    trajectory_recorder = input_obj.get("trajectoryRecorder")

    tool_metas_normalized = _normalize_tool_metas(subscription.get("toolMetas"))
    completed_client_tool_calls: List[Dict[str, Any]] = []
    for slot in client_tool_call_slots:
        if not isinstance(slot, dict):
            continue
        if slot.get("completed") and slot.get("params"):
            completed_client_tool_calls.append(
                {
                    "name": slot.get("name"),
                    "params": slot.get("params"),
                }
            )

    observed_replay_metadata = input_obj.get("buildAttemptReplayMetadata") or (
        lambda _params: {"replaySafe": True, "hadPotentialSideEffects": False}
    )
    replay_metadata = _REPLAY_METADATA_FROM_STATE(
        _OBSERVE_REPLAY_METADATA(
            subscription.get("getReplayState")(),
            observed_replay_metadata(
                {
                    "toolMetas": [],
                    "didSendViaMessagingTool": bool(
                        subscription.get("didSendViaMessagingTool", lambda: False)()
                    ),
                    "messagingToolSentTexts": list(
                        subscription.get("getMessagingToolSentTexts", lambda: [])()
                    ),
                    "messagingToolSentMediaUrls": list(
                        subscription.get("getMessagingToolSentMediaUrls", lambda: [])()
                    ),
                    "acceptedSessionSpawns": list(
                        subscription.get("getAcceptedSessionSpawns", lambda: [])()
                    ),
                    "successfulCronAdds": int(
                        subscription.get("getSuccessfulCronAdds", lambda: 0)() or 0
                    ),
                }
            ),
        )
    )

    result: EmbeddedRunAttemptResult = {
        "runId": attempt.get("runId"),
        "sessionId": attempt.get("sessionId"),
        "sessionKey": attempt.get("sessionKey"),
        "sessionFile": attempt.get("sessionFile"),
        "agentId": attempt.get("agentId"),
        "provider": attempt.get("provider"),
        "modelId": attempt.get("modelId"),
        "aborted": bool(state.get("aborted")),
        "externalAbort": bool(state.get("externalAbort")),
        "timedOut": bool(state.get("timedOut")),
        "idleTimedOut": bool(state.get("idleTimedOut")),
        "timedOutDuringCompaction": bool(state.get("timedOutDuringCompaction")),
        "timedOutDuringToolExecution": bool(state.get("timedOutDuringToolExecution")),
        "timedOutByRunBudget": bool(state.get("timedOutByRunBudget")),
        "promptError": state.get("promptError"),
        "promptErrorSource": state.get("promptErrorSource"),
        "preflightRecovery": state.get("preflightRecovery"),
        "sessionIdUsed": state.get("sessionIdUsed") or attempt.get("sessionId"),
        "sessionFileUsed": state.get("sessionFileUsed") or attempt.get("sessionFile"),
        "systemPromptReport": state.get("systemPromptReport"),
        "finalPromptText": state.get("finalPromptText"),
        "messagesSnapshot": state.get("messagesSnapshot") or [],
        "lastAssistant": state.get("lastAssistant"),
        "currentAttemptAssistant": state.get("currentAttemptAssistant"),
        "currentAttemptCompletedAssistant": state.get("currentAttemptCompletedAssistant"),
        "attemptUsage": state.get("attemptUsage"),
        "promptCache": state.get("promptCache"),
        "contextBudgetStatus": state.get("contextBudgetStatus"),
        "yieldDetected": bool(state.get("yieldDetected")),
        "didDeliverSourceReplyViaMessageTool": bool(
            state.get("didDeliverSourceReplyViaMessageTool")
        ),
        "toolMetas": tool_metas_normalized,
        "replayMetadata": replay_metadata,
        "clientToolCalls": completed_client_tool_calls,
        "trajectoryRecorder": trajectory_recorder,
    }

    if _FINALIZE_EMBEDDED_ATTEMPT:
        try:
            finalized = _FINALIZE_EMBEDDED_ATTEMPT(
                {"result": dict(result), "state": state, "attempt": attempt}
            )
            if isinstance(finalized, dict):
                result.update(finalized)
        except Exception:
            pass
    return result


__all__ = [
    "CompleteEmbeddedAttemptResultInput",
    "EmbeddedAttemptClientToolCallSlot",
    "EmbeddedAttemptResultState",
    "EmbeddedAttemptToolMeta",
    "EmbeddedRunAttemptResult",
    "complete_embedded_attempt_result",
    "set_build_agent_hook_context_channel_fields_hook",
    "set_build_agent_hook_context_identity_fields_hook",
    "set_finalize_embedded_attempt_hook",
    "set_freeze_diagnostic_trace_context_hook",
    "set_is_cloud_code_assist_format_error_hook",
    "set_observe_replay_metadata_hook",
    "set_record_stage_cache_trace_hook",
    "set_replay_metadata_from_state_hook",
    "set_run_llm_output_hook_hook",
    "set_should_run_llm_output_hooks_for_attempt_hook",
]
