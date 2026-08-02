"""jarvis.agents.embedded_agent_runner.run.incomplete_turn — classify incomplete terminal assistant turns and retry instructions.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/incomplete-turn.ts``.

Public surface (mirrors the OpenClaw source):

Constants:

- :data:`DEFAULT_REASONING_ONLY_RETRY_LIMIT`
- :data:`DEFAULT_EMPTY_RESPONSE_RETRY_LIMIT`
- :data:`RETRY_GUARD_MODEL_APIS`
- :data:`GEMINI_INCOMPLETE_TURN_PROVIDER_IDS`
- :data:`REASONING_ONLY_RETRY_INSTRUCTION`
- :data:`EMPTY_RESPONSE_RETRY_INSTRUCTION`
- :data:`TOOL_USE_TERMINAL_CONTINUATION_INSTRUCTION`

Functions:

- :func:`is_incomplete_terminal_assistant_turn`
- :func:`build_attempt_replay_metadata`
- :func:`resolve_attempt_replay_metadata`
- :func:`has_attempt_terminal_state`
- :func:`resolve_incomplete_turn_payload_text`
- :func:`should_retry_missing_assistant_turn`
- :func:`resolve_silent_tool_result_reply_payload`
- :func:`resolve_replay_invalid_flag`
- :func:`resolve_run_liveness_state`
- :func:`should_retry_silent_error_assistant_turn`
- :func:`should_treat_empty_assistant_reply_as_silent`
- :func:`resolve_reasoning_only_retry_instruction`
- :func:`resolve_tool_use_terminal_continuation_instruction`
- :func:`resolve_empty_response_retry_instruction`

Phase 7.6b-1 — focused minimal port.

The OpenClaw source is ~30K and tightly coupled to the agent-runner
types, delivery-evidence, accepted-session-spawn, and provider-shape
layers. The Python port keeps the public surface and delegates the
heavy classification logic to installable hooks so the host can plug
in the real layers as they land.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Set


#: Default reasoning-only retry limit. Mirrors
#: :data:`DEFAULT_REASONING_ONLY_RETRY_LIMIT` (``incomplete-turn.ts:134``).
DEFAULT_REASONING_ONLY_RETRY_LIMIT: int = 2


#: Default empty-response retry limit. Mirrors
#: :data:`DEFAULT_EMPTY_RESPONSE_RETRY_LIMIT` (``incomplete-turn.ts:135``).
DEFAULT_EMPTY_RESPONSE_RETRY_LIMIT: int = 1


#: Reasoning-only retry instruction. Mirrors
#: ``REASONING_ONLY_RETRY_INSTRUCTION`` (``incomplete-turn.ts:136-137``).
REASONING_ONLY_RETRY_INSTRUCTION: str = (
    "The previous assistant turn recorded reasoning but did not produce a "
    "user-visible answer. Continue from that partial turn and produce the "
    "visible answer now. Do not restate the reasoning or restart from scratch."
)


#: Empty-response retry instruction. Mirrors
#: ``EMPTY_RESPONSE_RETRY_INSTRUCTION`` (``incomplete-turn.ts:138-139``).
EMPTY_RESPONSE_RETRY_INSTRUCTION: str = (
    "The previous attempt did not produce a user-visible answer. Continue "
    "from the current state and produce the visible answer now. Do not "
    "restart from scratch."
)


#: Tool-use terminal continuation instruction. Mirrors
#: ``TOOL_USE_TERMINAL_CONTINUATION_INSTRUCTION`` (``incomplete-turn.ts:140-141``).
TOOL_USE_TERMINAL_CONTINUATION_INSTRUCTION: str = (
    "The previous assistant turn completed its tool calls but did not "
    "produce a user-visible answer. Continue from the current transcript "
    "and produce the final user-visible answer now. Do not repeat completed "
    "tool calls or restart from scratch."
)


#: Model APIs eligible for the non-visible turn retry guard. Mirrors
#: ``RETRY_GUARD_MODEL_APIS`` (``incomplete-turn.ts:122-131``).
RETRY_GUARD_MODEL_APIS: Set[str] = {
    "openai-completions",
    "anthropic-messages",
    "bedrock-converse-stream",
    "openai-responses",
    "openai-chatgpt-responses",
    "azure-openai-responses",
    "openclaw-openai-responses-transport",
    "openclaw-azure-openai-responses-transport",
}


#: Gemini provider ids that need the incomplete-turn guard. Mirrors
#: ``GEMINI_INCOMPLETE_TURN_PROVIDER_IDS`` (``incomplete-turn.ts:110-115``).
GEMINI_INCOMPLETE_TURN_PROVIDER_IDS: Set[str] = {
    "google",
    "google-vertex",
    "google-antigravity",
    "google-gemini-cli",
}


#: Gemini model-id pattern. Mirrors
#: ``GEMINI_INCOMPLETE_TURN_MODEL_ID_PATTERN`` (``incomplete-turn.ts:116``).
GEMINI_INCOMPLETE_TURN_MODEL_ID_PATTERN: "re.Pattern[str]" = re.compile(
    r"^gemini(?:[.\-]|$)"
)


#: Ollama provider-id pattern. Mirrors
#: ``OLLAMA_INCOMPLETE_TURN_PROVIDER_ID_PATTERN`` (``incomplete-turn.ts:118``).
OLLAMA_INCOMPLETE_TURN_PROVIDER_ID_PATTERN: "re.Pattern[str]" = re.compile(
    r"^ollama(?:-|$)"
)


#: Replay-unsafe fallback metadata. Mirrors
#: ``REPLAY_UNSAFE_FALLBACK_METADATA`` (``incomplete-turn.ts:94-97``).
REPLAY_UNSAFE_FALLBACK_METADATA: Dict[str, Any] = {
    "hadPotentialSideEffects": True,
    "replaySafe": False,
}


#: User-visible payload text when the attempt had potential side effects.
#: Mirrors the OpenClaw source's :func:`resolveIncompleteTurnPayloadText`
#: final branch (``incomplete-turn.ts:299-301``).
INCOMPLETE_TURN_WITH_SIDE_EFFECTS_TEXT: str = (
    "⚠️ Agent couldn't generate a response. Note: some tool actions may "
    "have already been executed — please verify before retrying."
)


#: User-visible payload text when the attempt had no potential side effects.
INCOMPLETE_TURN_PLAIN_TEXT: str = (
    "⚠️ Agent couldn't generate a response. Please try again."
)


#: Type alias for the attempt shape used by replay-metadata builders.
ReplayMetadataAttempt = Dict[str, Any]


#: Type alias for the attempt shape used by terminal-state classification.
TerminalAttemptState = Dict[str, Any]


#: Type alias for the attempt shape used by incomplete-turn classification.
IncompleteTurnAttempt = Dict[str, Any]


#: Type alias for the attempt shape used by liveness classification.
RunLivenessAttempt = Dict[str, Any]


#: Type alias for the attempt shape used by silent-tool-result classification.
SilentToolResultAttempt = Dict[str, Any]


#: Type alias for the assistant turn result (subset of
#: :class:`EmbeddedRunAttemptResult`).
AssistantMessage = Dict[str, Any]


# ---------------------------------------------------------------------------
# Installable hooks
# ---------------------------------------------------------------------------


#: Hook for ``isIncompleteTerminalAssistantTurn`` (stopReason-based
#: gate). Mirrors the small inline function in
#: ``incomplete-turn.ts:99-108``.
_IS_INCOMPLETE_TERMINAL_ASSISTANT_TURN: Callable[[Dict[str, Any]], bool] = (
    lambda params: _default_is_incomplete_terminal_assistant_turn(params)
)


def set_is_incomplete_terminal_assistant_turn_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom isIncompleteTerminalAssistantTurn hook."""
    global _IS_INCOMPLETE_TERMINAL_ASSISTANT_TURN
    _IS_INCOMPLETE_TERMINAL_ASSISTANT_TURN = hook


def _default_is_incomplete_terminal_assistant_turn(params: Dict[str, Any]) -> bool:
    last_assistant = params.get("lastAssistant") or {}
    stop_reason = last_assistant.get("stopReason")
    if stop_reason == "toolUse":
        return True
    if stop_reason == "length" and not params.get("hasTerminalOutput", False):
        return True
    return False


#: Hook for ``buildAttemptReplayMetadata``. Mirrors
#: ``incomplete-turn.ts:148-163``.
_BUILD_ATTEMPT_REPLAY_METADATA: Callable[[Dict[str, Any]], Dict[str, Any]] = (
    lambda params: _default_build_attempt_replay_metadata(params)
)


def set_build_attempt_replay_metadata_hook(
    hook: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> None:
    """Install a custom buildAttemptReplayMetadata hook."""
    global _BUILD_ATTEMPT_REPLAY_METADATA
    _BUILD_ATTEMPT_REPLAY_METADATA = hook


def _default_build_attempt_replay_metadata(params: Dict[str, Any]) -> Dict[str, Any]:
    tool_metas = params.get("toolMetas") or []
    had_unsafe_tools = any(
        (entry or {}).get("replaySafe") is not True for entry in tool_metas
    )
    had_async_started_tool = any(
        (entry or {}).get("asyncStarted") is True for entry in tool_metas
    )
    had_messaging_delivery = bool(params.get("didSendViaMessagingTool"))
    had_session_spawn = bool(params.get("acceptedSessionSpawns"))
    had_cron_adds = (params.get("successfulCronAdds") or 0) > 0
    had_potential_side_effects = (
        had_unsafe_tools
        or had_async_started_tool
        or had_messaging_delivery
        or had_session_spawn
        or had_cron_adds
    )
    return {
        "hadPotentialSideEffects": had_potential_side_effects,
        "replaySafe": not had_potential_side_effects,
    }


#: Hook for ``hasAttemptTerminalState``. Mirrors
#: ``incomplete-turn.ts:199-221``.
_HAS_ATTEMPT_TERMINAL_STATE: Callable[[Dict[str, Any]], bool] = (
    lambda attempt: _default_has_attempt_terminal_state(attempt)
)


def set_has_attempt_terminal_state_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom hasAttemptTerminalState hook."""
    global _HAS_ATTEMPT_TERMINAL_STATE
    _HAS_ATTEMPT_TERMINAL_STATE = hook


def _default_has_attempt_terminal_state(attempt: Dict[str, Any]) -> bool:
    if attempt.get("clientToolCalls"):
        return True
    if attempt.get("yieldDetected"):
        return True
    if attempt.get("didSendDeterministicApprovalPrompt"):
        return True
    if attempt.get("heartbeatToolResponse"):
        return True
    if attempt.get("lastToolError"):
        return True
    media_urls = attempt.get("toolMediaUrls") or []
    if any((url or "").strip() for url in media_urls):
        return True
    if attempt.get("toolAudioAsVoice"):
        return True
    if attempt.get("toolTrustedLocalMedia"):
        return True
    if attempt.get("hasToolMediaBlockReply"):
        return True
    if attempt.get("didDeliverSourceReplyViaMessageTool"):
        return True
    if (attempt.get("messagingToolSourceReplyPayloads") or []):
        return True
    sent_texts = attempt.get("messagingToolSentTexts") or []
    sent_media = attempt.get("messagingToolSentMediaUrls") or []
    sent_targets = attempt.get("messagingToolSentTargets") or []
    if sent_texts or sent_media or sent_targets:
        return True
    if attempt.get("acceptedSessionSpawns"):
        return True
    tool_metas = attempt.get("toolMetas") or []
    if any((entry or {}).get("asyncStarted") is True for entry in tool_metas):
        return True
    if (attempt.get("successfulCronAdds") or 0) > 0:
        return True
    return False


#: Hook for the hasCommittedMessagingToolDeliveryEvidence gate. Mirrors
#: the OpenClaw source's delivery-evidence check.
_HAS_COMMITTED_MESSAGING_TOOL_DELIVERY: Callable[[Dict[str, Any]], bool] = (
    lambda attempt: _default_has_committed_messaging_tool_delivery(attempt)
)


def set_has_committed_messaging_tool_delivery_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom delivery-evidence check hook."""
    global _HAS_COMMITTED_MESSAGING_TOOL_DELIVERY
    _HAS_COMMITTED_MESSAGING_TOOL_DELIVERY = hook


def _default_has_committed_messaging_tool_delivery(attempt: Dict[str, Any]) -> bool:
    if attempt.get("didDeliverSourceReplyViaMessageTool"):
        return True
    if attempt.get("messagingToolSourceReplyPayloads"):
        return True
    sent_texts = attempt.get("messagingToolSentTexts") or []
    sent_media = attempt.get("messagingToolSentMediaUrls") or []
    sent_targets = attempt.get("messagingToolSentTargets") or []
    return bool(sent_texts or sent_media or sent_targets)


#: Hook for the hasAcceptedSessionSpawn gate.
_HAS_ACCEPTED_SESSION_SPAWN: Callable[[Optional[List[Any]]], bool] = (
    lambda spawns: _default_has_accepted_session_spawn(spawns)
)


def set_has_accepted_session_spawn_hook(
    hook: Callable[[Optional[List[Any]]], bool],
) -> None:
    """Install a custom accepted-session-spawn check hook."""
    global _HAS_ACCEPTED_SESSION_SPAWN
    _HAS_ACCEPTED_SESSION_SPAWN = hook


def _default_has_accepted_session_spawn(
    spawns: Optional[List[Any]],
) -> bool:
    return bool(spawns)


#: Hook for the hasAsyncStartedToolActivity gate.
_HAS_ASYNC_STARTED_TOOL_ACTIVITY: Callable[[Optional[List[Any]]], bool] = (
    lambda tool_metas: _default_has_async_started_tool_activity(tool_metas)
)


def set_has_async_started_tool_activity_hook(
    hook: Callable[[Optional[List[Any]]], bool],
) -> None:
    """Install a custom async-started-tool-activity check hook."""
    global _HAS_ASYNC_STARTED_TOOL_ACTIVITY
    _HAS_ASYNC_STARTED_TOOL_ACTIVITY = hook


def _default_has_async_started_tool_activity(
    tool_metas: Optional[List[Any]],
) -> bool:
    if not tool_metas:
        return False
    return any((entry or {}).get("asyncStarted") is True for entry in tool_metas)


#: Hook for the hasOnlyAssistantReasoningContent gate.
_HAS_ONLY_ASSISTANT_REASONING_CONTENT: Callable[[Optional[Dict[str, Any]]], bool] = (
    lambda assistant: _default_has_only_assistant_reasoning_content(assistant)
)


def set_has_only_assistant_reasoning_content_hook(
    hook: Callable[[Optional[Dict[str, Any]]], bool],
) -> None:
    """Install a custom reasoning-only assistant check hook."""
    global _HAS_ONLY_ASSISTANT_REASONING_CONTENT
    _HAS_ONLY_ASSISTANT_REASONING_CONTENT = hook


def _default_has_only_assistant_reasoning_content(
    assistant: Optional[Dict[str, Any]],
) -> bool:
    if not assistant:
        return False
    content = assistant.get("content")
    if not content or not isinstance(content, list):
        return False
    if not content:
        return False
    for block in content:
        if not isinstance(block, dict):
            return False
        kind = block.get("type") or block.get("kind")
        if kind not in ("thinking", "reasoning"):
            return False
    return True


#: Hook for the isReasoningOnlyAssistantTurn gate.
_IS_REASONING_ONLY_ASSISTANT_TURN: Callable[[Optional[Dict[str, Any]]], bool] = (
    lambda assistant: _default_is_reasoning_only_assistant_turn(assistant)
)


def set_is_reasoning_only_assistant_turn_hook(
    hook: Callable[[Optional[Dict[str, Any]]], bool],
) -> None:
    """Install a custom reasoning-only-turn check hook."""
    global _IS_REASONING_ONLY_ASSISTANT_TURN
    _IS_REASONING_ONLY_ASSISTANT_TURN = hook


def _default_is_reasoning_only_assistant_turn(
    assistant: Optional[Dict[str, Any]],
) -> bool:
    if not assistant:
        return False
    return _HAS_ONLY_ASSISTANT_REASONING_CONTENT(assistant)


#: Hook for the isEmptyResponseAssistantTurn gate.
_IS_EMPTY_RESPONSE_ASSISTANT_TURN: Callable[[Dict[str, Any]], bool] = (
    lambda params: _default_is_empty_response_assistant_turn(params)
)


def set_is_empty_response_assistant_turn_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom empty-response check hook."""
    global _IS_EMPTY_RESPONSE_ASSISTANT_TURN
    _IS_EMPTY_RESPONSE_ASSISTANT_TURN = hook


def _default_is_empty_response_assistant_turn(params: Dict[str, Any]) -> bool:
    attempt = params.get("attempt") or {}
    assistant_texts = attempt.get("assistantTexts") or []
    if _join_assistant_texts(assistant_texts).strip():
        return False
    if attempt.get("clientToolCalls"):
        return False
    if attempt.get("didSendDeterministicApprovalPrompt"):
        return False
    if attempt.get("yieldDetected"):
        return False
    if attempt.get("lastToolError"):
        return False
    if attempt.get("didDeliverSourceReplyViaMessageTool"):
        return False
    if attempt.get("messagingToolSourceReplyPayloads"):
        return False
    return params.get("payloadCount", 0) == 0


#: Hook for the hasOnlySilentAssistantReply gate.
_HAS_ONLY_SILENT_ASSISTANT_REPLY: Callable[[Optional[List[Any]]], bool] = (
    lambda texts: _default_has_only_silent_assistant_reply(texts)
)


def set_has_only_silent_assistant_reply_hook(
    hook: Callable[[Optional[List[Any]]], bool],
) -> None:
    """Install a custom silent-reply check hook."""
    global _HAS_ONLY_SILENT_ASSISTANT_REPLY
    _HAS_ONLY_SILENT_ASSISTANT_REPLY = hook


def _default_has_only_silent_assistant_reply(
    texts: Optional[List[Any]],
) -> bool:
    if not texts:
        return False
    return all(_IS_SILENT_REPLY_TEXT(text) for text in texts)


#: Hook for the isSilentReplyText / isSilentReplyPayloadText gates.
_IS_SILENT_REPLY_TEXT: Callable[[Optional[str]], bool] = (
    lambda text: _default_is_silent_reply_text(text)
)


def set_is_silent_reply_text_hook(
    hook: Callable[[Optional[str]], bool],
) -> None:
    """Install a custom silent-reply text check hook."""
    global _IS_SILENT_REPLY_TEXT
    _IS_SILENT_REPLY_TEXT = hook


def _default_is_silent_reply_text(text: Optional[str]) -> bool:
    if not text:
        return False
    return "SILENT_REPLY_TOKEN" in text or text.strip() == "‎"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _join_assistant_texts(texts: Optional[List[Any]]) -> str:
    if not texts:
        return ""
    parts: List[str] = []
    for text in texts:
        if text is None:
            continue
        parts.append(str(text))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_incomplete_terminal_assistant_turn(
    params: Dict[str, Any],
) -> bool:
    """Return True when the last assistant turn is incomplete.

    Mirrors :func:`isIncompleteTerminalAssistantTurn`
    (``incomplete-turn.ts:99-108``).
    """
    return _IS_INCOMPLETE_TERMINAL_ASSISTANT_TURN(dict(params or {}))


def build_attempt_replay_metadata(
    params: ReplayMetadataAttempt,
) -> Dict[str, Any]:
    """Build the replay-metadata for an attempt.

    Mirrors :func:`buildAttemptReplayMetadata`
    (``incomplete-turn.ts:148-163``).
    """
    return _BUILD_ATTEMPT_REPLAY_METADATA(dict(params or {}))


def resolve_attempt_replay_metadata(
    attempt: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve replay-metadata with a fallback to the unsafe default.

    Mirrors :func:`resolveAttemptReplayMetadata`
    (``incomplete-turn.ts:165-170``).
    """
    replay_metadata = (attempt or {}).get("replayMetadata")
    if replay_metadata is None:
        return dict(REPLAY_UNSAFE_FALLBACK_METADATA)
    return dict(replay_metadata)


def has_attempt_terminal_state(
    attempt: TerminalAttemptState,
) -> bool:
    """Return True when the attempt has any committed side-effect.

    Mirrors :func:`hasAttemptTerminalState`
    (``incomplete-turn.ts:199-221``).
    """
    return _HAS_ATTEMPT_TERMINAL_STATE(dict(attempt or {}))


def resolve_incomplete_turn_payload_text(
    params: Dict[str, Any],
) -> Optional[str]:
    """Build the user-visible incomplete-turn warning text.

    Mirrors :func:`resolveIncompleteTurnPayloadText`
    (``incomplete-turn.ts:228-302``).
    """
    attempt = params.get("attempt") or {}
    payload_count = int(params.get("payloadCount", 0) or 0)
    aborted = bool(params.get("aborted"))
    external_abort = bool(params.get("externalAbort"))
    timed_out = bool(params.get("timedOut"))
    assistant = attempt.get("currentAttemptAssistant") or attempt.get("lastAssistant")
    has_terminal_output = has_attempt_terminal_state(attempt)
    incomplete = is_incomplete_terminal_assistant_turn(
        {
            "hasAssistantVisibleText": payload_count > 0,
            "hasTerminalOutput": has_terminal_output,
            "lastAssistant": assistant,
        }
    )
    assistant_texts = attempt.get("assistantTexts") or []
    thinking_only_terminal = (
        payload_count != 0
        and not _join_assistant_texts(assistant_texts).strip()
        and not has_terminal_output
        and bool(assistant)
        and _HAS_ONLY_ASSISTANT_REASONING_CONTENT(assistant)
    )
    if (
        (payload_count != 0 and not incomplete and not thinking_only_terminal)
        or (aborted and external_abort)
        or timed_out
        or attempt.get("clientToolCalls")
        or attempt.get("yieldDetected")
        or attempt.get("didSendDeterministicApprovalPrompt")
        or attempt.get("lastToolError")
    ):
        return None
    if _HAS_ONLY_SILENT_ASSISTANT_REPLY(assistant_texts):
        return None
    if _HAS_COMMITTED_MESSAGING_TOOL_DELIVERY(attempt):
        return None
    if _HAS_ACCEPTED_SESSION_SPAWN(attempt.get("acceptedSessionSpawns")):
        return None
    if _HAS_ASYNC_STARTED_TOOL_ACTIVITY(attempt.get("toolMetas")):
        return None
    stop_reason = (assistant or {}).get("stopReason")
    reasoning_only_assistant = _IS_REASONING_ONLY_ASSISTANT_TURN(assistant)
    empty_response_assistant = _IS_EMPTY_RESPONSE_ASSISTANT_TURN(
        {"payloadCount": payload_count, "attempt": attempt}
    )
    if (
        not incomplete
        and not reasoning_only_assistant
        and not thinking_only_terminal
        and not empty_response_assistant
        and stop_reason != "error"
    ):
        return None
    if resolve_attempt_replay_metadata(attempt).get("hadPotentialSideEffects"):
        return INCOMPLETE_TURN_WITH_SIDE_EFFECTS_TEXT
    return INCOMPLETE_TURN_PLAIN_TEXT


def should_retry_missing_assistant_turn(
    params: Dict[str, Any],
) -> bool:
    """Return True when the missing-assistant turn is safe to retry.

    Mirrors :func:`shouldRetryMissingAssistantTurn`
    (``incomplete-turn.ts:309-...``).
    """
    attempt = params.get("attempt") or {}
    payload_count = int(params.get("payloadCount", 0) or 0)
    aborted = bool(params.get("aborted"))
    prompt_error = params.get("promptError")
    timed_out = bool(params.get("timedOut"))
    if (
        payload_count != 0
        or aborted
        or bool(prompt_error)
        or timed_out
        or attempt.get("clientToolCalls")
        or attempt.get("currentAttemptAssistant")
        or attempt.get("lastAssistant")
        or attempt.get("yieldDetected")
        or attempt.get("didSendDeterministicApprovalPrompt")
        or attempt.get("lastToolError")
    ):
        return False
    assistant_texts = attempt.get("assistantTexts") or []
    if _HAS_ONLY_SILENT_ASSISTANT_REPLY(assistant_texts):
        return False
    if _join_assistant_texts(assistant_texts).strip():
        return False
    if _HAS_COMMITTED_MESSAGING_TOOL_DELIVERY(attempt):
        return False
    if _HAS_ACCEPTED_SESSION_SPAWN(attempt.get("acceptedSessionSpawns")):
        return False
    if _HAS_ASYNC_STARTED_TOOL_ACTIVITY(attempt.get("toolMetas")):
        return False
    return True


def resolve_silent_tool_result_reply_payload(
    params: Dict[str, Any],
) -> Optional[str]:
    """Resolve the silent-tool-result reply payload text.

    Mirrors :func:`resolveSilentToolResultReplyPayload`
    (``incomplete-turn.ts:...``).
    """
    attempt = params.get("attempt") or {}
    messages = params.get("messagesSnapshot") or []
    tool_metas = attempt.get("toolMetas") or []
    if attempt.get("clientToolCalls"):
        return None
    if attempt.get("didSendDeterministicApprovalPrompt"):
        return None
    if attempt.get("yieldDetected"):
        return None
    if attempt.get("lastToolError"):
        return None
    if not _has_trailing_silent_tool_result(messages):
        return None
    if _HAS_ASYNC_STARTED_TOOL_ACTIVITY(tool_metas):
        return None
    assistant_texts = attempt.get("assistantTexts") or []
    return _join_assistant_texts(assistant_texts) or ""


def _has_trailing_silent_tool_result(messages: List[Any]) -> bool:
    if not messages:
        return False
    last = messages[-1]
    if not isinstance(last, dict):
        return False
    role = last.get("role")
    if role != "toolResult":
        return False
    content = last.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                text = block.get("text") or ""
                if text and not _IS_SILENT_REPLY_TEXT(text):
                    return False
        return True
    if isinstance(content, str):
        return _IS_SILENT_REPLY_TEXT(content)
    return False


def resolve_replay_invalid_flag(
    params: Dict[str, Any],
) -> bool:
    """Return True when the attempt's replay metadata is invalid.

    Mirrors :func:`resolveReplayInvalidFlag`
    (``incomplete-turn.ts:...``).
    """
    attempt = params.get("attempt") or {}
    replay = resolve_attempt_replay_metadata(attempt)
    return not bool(replay.get("replaySafe"))


def resolve_run_liveness_state(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Return the liveness-state descriptor for the run.

    Mirrors :func:`resolveRunLivenessState`
    (``incomplete-turn.ts:...``).
    """
    attempt = params.get("attempt") or {}
    return {
        "hasAssistant": bool(attempt.get("lastAssistant") or attempt.get("currentAttemptAssistant")),
        "hasPromptError": attempt.get("promptErrorSource") is not None,
        "hasReplayMetadata": attempt.get("replayMetadata") is not None,
        "timedOutDuringCompaction": bool(attempt.get("timedOutDuringCompaction")),
    }


def should_retry_silent_error_assistant_turn(
    params: Dict[str, Any],
) -> bool:
    """Return True when a silent-error turn is safe to retry.

    Mirrors :func:`shouldRetrySilentErrorAssistantTurn`
    (``incomplete-turn.ts:...``).
    """
    attempt = params.get("attempt") or {}
    if attempt.get("didSendDeterministicApprovalPrompt"):
        return False
    if attempt.get("yieldDetected"):
        return False
    if attempt.get("lastToolError"):
        return False
    if _HAS_COMMITTED_MESSAGING_TOOL_DELIVERY(attempt):
        return False
    if _HAS_ACCEPTED_SESSION_SPAWN(attempt.get("acceptedSessionSpawns")):
        return False
    assistant_texts = attempt.get("assistantTexts") or []
    if not _HAS_ONLY_SILENT_ASSISTANT_REPLY(assistant_texts):
        return False
    return True


def should_treat_empty_assistant_reply_as_silent(
    params: Dict[str, Any],
) -> bool:
    """Return True when an empty assistant reply should be treated as silent.

    Mirrors :func:`shouldTreatEmptyAssistantReplyAsSilent`
    (``incomplete-turn.ts:...``).
    """
    attempt = params.get("attempt") or {}
    assistant_texts = attempt.get("assistantTexts") or []
    if _join_assistant_texts(assistant_texts).strip():
        return False
    if attempt.get("clientToolCalls"):
        return False
    if attempt.get("didSendDeterministicApprovalPrompt"):
        return False
    if attempt.get("yieldDetected"):
        return False
    if attempt.get("lastToolError"):
        return False
    if attempt.get("didDeliverSourceReplyViaMessageTool"):
        return False
    if attempt.get("messagingToolSourceReplyPayloads"):
        return False
    return True


def resolve_reasoning_only_retry_instruction(
    params: Dict[str, Any],
) -> Optional[str]:
    """Resolve the reasoning-only retry instruction.

    Mirrors :func:`resolveReasoningOnlyRetryInstruction`
    (``incomplete-turn.ts:...``).
    """
    if not bool(params.get("eligible", False)):
        return None
    return REASONING_ONLY_RETRY_INSTRUCTION


def resolve_tool_use_terminal_continuation_instruction(
    params: Dict[str, Any],
) -> Optional[str]:
    """Resolve the tool-use terminal continuation instruction.

    Mirrors :func:`resolveToolUseTerminalContinuationInstruction`
    (``incomplete-turn.ts:...``).
    """
    if not bool(params.get("eligible", False)):
        return None
    return TOOL_USE_TERMINAL_CONTINUATION_INSTRUCTION


def resolve_empty_response_retry_instruction(
    params: Dict[str, Any],
) -> Optional[str]:
    """Resolve the empty-response retry instruction.

    Mirrors :func:`resolveEmptyResponseRetryInstruction`
    (``incomplete-turn.ts:...``).
    """
    if not bool(params.get("eligible", False)):
        return None
    return EMPTY_RESPONSE_RETRY_INSTRUCTION


__all__ = [
    "DEFAULT_EMPTY_RESPONSE_RETRY_LIMIT",
    "DEFAULT_REASONING_ONLY_RETRY_LIMIT",
    "EMPTY_RESPONSE_RETRY_INSTRUCTION",
    "GEMINI_INCOMPLETE_TURN_MODEL_ID_PATTERN",
    "GEMINI_INCOMPLETE_TURN_PROVIDER_IDS",
    "INCOMPLETE_TURN_PLAIN_TEXT",
    "INCOMPLETE_TURN_WITH_SIDE_EFFECTS_TEXT",
    "OLLAMA_INCOMPLETE_TURN_PROVIDER_ID_PATTERN",
    "REASONING_ONLY_RETRY_INSTRUCTION",
    "REPLAY_UNSAFE_FALLBACK_METADATA",
    "RETRY_GUARD_MODEL_APIS",
    "TOOL_USE_TERMINAL_CONTINUATION_INSTRUCTION",
    "build_attempt_replay_metadata",
    "has_attempt_terminal_state",
    "is_incomplete_terminal_assistant_turn",
    "resolve_attempt_replay_metadata",
    "resolve_empty_response_retry_instruction",
    "resolve_incomplete_turn_payload_text",
    "resolve_reasoning_only_retry_instruction",
    "resolve_replay_invalid_flag",
    "resolve_run_liveness_state",
    "resolve_silent_tool_result_reply_payload",
    "resolve_tool_use_terminal_continuation_instruction",
    "set_build_attempt_replay_metadata_hook",
    "set_has_accepted_session_spawn_hook",
    "set_has_async_started_tool_activity_hook",
    "set_has_attempt_terminal_state_hook",
    "set_has_committed_messaging_tool_delivery_hook",
    "set_has_only_assistant_reasoning_content_hook",
    "set_has_only_silent_assistant_reply_hook",
    "set_is_empty_response_assistant_turn_hook",
    "set_is_incomplete_terminal_assistant_turn_hook",
    "set_is_reasoning_only_assistant_turn_hook",
    "set_is_silent_reply_text_hook",
    "should_retry_missing_assistant_turn",
    "should_retry_silent_error_assistant_turn",
    "should_treat_empty_assistant_reply_as_silent",
]
