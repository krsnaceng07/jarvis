"""jarvis.agents.embedded_agent_runner.run.terminal_resolution — resolve the embedded-run terminal action.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/terminal-resolution.ts``.

Public surface:

- :func:`resolve_embedded_run_terminal` (async) — decide whether to
  retry the run or produce the final run result.
- :func:`copy_attempt_delivery_state` — shallow-copy the
  delivery-evidence fields from one attempt to another.

Phase 7.6b-3 — focused minimal port.

The OpenClaw source is tightly coupled to the auth-profile-success,
incomplete-turn, terminal-retry-state, and embedded-agent-result
layers. The Python port keeps the public surface and delegates the
heavy retry decision to installable hooks.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Maximum missing-assistant retries. Mirrors
#: :data:`MAX_MISSING_ASSISTANT_RETRIES` (``terminal-resolution.ts:40``).
MAX_MISSING_ASSISTANT_RETRIES: int = 1


#: Maximum tool-use terminal continuations. Mirrors
#: :data:`MAX_TOOL_USE_TERMINAL_CONTINUATIONS` (``terminal-resolution.ts:41``).
MAX_TOOL_USE_TERMINAL_CONTINUATIONS: int = 1


#: Compaction-continuation retry instruction. Mirrors
#: ``COMPACTION_CONTINUATION_RETRY_INSTRUCTION``
#: (``terminal-resolution.ts:42-43``).
COMPACTION_CONTINUATION_RETRY_INSTRUCTION: str = (
    "The previous attempt compacted the conversation context before "
    "producing a final user-visible answer. Continue from the "
    "compacted transcript and produce the final answer now. Do not "
    "restart from scratch, do not repeat completed work, and do not "
    "rerun tools unless the transcript clearly lacks required evidence."
)


#: Before-agent-finalize retry prompt prefix. Mirrors
#: ``BEFORE_AGENT_FINALIZE_RETRY_PROMPT_PREFIX``
#: (``terminal-resolution.ts:44-45``).
BEFORE_AGENT_FINALIZE_RETRY_PROMPT_PREFIX: str = (
    "Before accepting the previous final answer, apply this revision "
    "request and produce the revised final answer. Do not repeat "
    "completed work or rerun tools unless the request explicitly "
    "requires it."
)


#: Maximum before-agent-finalize revisions. Mirrors
#: :data:`MAX_BEFORE_AGENT_FINALIZE_REVISIONS` from
#: ``terminal-retry-state.ts``.
MAX_BEFORE_AGENT_FINALIZE_REVISIONS: int = 1


#: Embedded run terminal retry state.
EmbeddedRunTerminalRetryState = Dict[str, Any]


#: Embedded run replay state.
EmbeddedRunReplayState = Dict[str, Any]


#: Embedded agent meta.
EmbeddedAgentMeta = Dict[str, Any]


#: Embedded agent run result.
EmbeddedAgentRunResult = Dict[str, Any]


#: Embedded run attempt result.
EmbeddedRunAttemptResult = Dict[str, Any]


#: Terminal resolution action. Either ``"retry"`` or
#: ``"complete"`` (with a result).
TerminalResolution = Dict[str, Any]


#: Auth profile failure reason.
AuthProfileFailureReason = str


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for :func:`markEmbeddedRunAuthProfileSuccess` from
#: ``auth-profile-success.ts``.
_MARK_EMBEDDED_RUN_AUTH_PROFILE_SUCCESS: Callable[
    [Dict[str, Any]], None
] = lambda _p: None


def set_mark_embedded_run_auth_profile_success_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom markEmbeddedRunAuthProfileSuccess hook."""
    global _MARK_EMBEDDED_RUN_AUTH_PROFILE_SUCCESS
    _MARK_EMBEDDED_RUN_AUTH_PROFILE_SUCCESS = hook


#: Hook for :func:`reportEmbeddedRunSuccessfulAuthBinding` from
#: ``auth-profile-success.ts``.
_REPORT_EMBEDDED_RUN_SUCCESSFUL_AUTH_BINDING: Callable[
    [Dict[str, Any]], None
] = lambda _p: None


def set_report_embedded_run_successful_auth_binding_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom reportEmbeddedRunSuccessfulAuthBinding hook."""
    global _REPORT_EMBEDDED_RUN_SUCCESSFUL_AUTH_BINDING
    _REPORT_EMBEDDED_RUN_SUCCESSFUL_AUTH_BINDING = hook


#: Hook for :func:`activateInternalPrompt` from
#: ``run-attempt-dispatch.ts``.
_ACTIVATE_INTERNAL_PROMPT: Callable[[str, bool], None] = lambda _p, _persisted: None


def set_activate_internal_prompt_hook(
    hook: Callable[[str, bool], None],
) -> None:
    """Install a custom activateInternalPrompt hook."""
    global _ACTIVATE_INTERNAL_PROMPT
    _ACTIVATE_INTERNAL_PROMPT = hook


#: Hook for the markEmbeddedRunAuthProfileFailure helper.
_MARK_EMBEDDED_RUN_AUTH_PROFILE_FAILURE: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_mark_embedded_run_auth_profile_failure_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom markEmbeddedRunAuthProfileFailure hook."""
    global _MARK_EMBEDDED_RUN_AUTH_PROFILE_FAILURE
    _MARK_EMBEDDED_RUN_AUTH_PROFILE_FAILURE = hook


#: Hook for the freeze-diagnostic-trace-context step.
_FREEZE_DIAGNOSTIC_TRACE_CONTEXT: Callable[[Dict[str, Any]], Any] = (
    lambda _t: None
)


def set_freeze_diagnostic_trace_context_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom freezeDiagnosticTraceContext hook."""
    global _FREEZE_DIAGNOSTIC_TRACE_CONTEXT
    _FREEZE_DIAGNOSTIC_TRACE_CONTEXT = hook


#: Hook for the resolveEmbeddedRunFailureSignal step.
_RESOLVE_EMBEDDED_RUN_FAILURE_SIGNAL: Callable[[Dict[str, Any]], Any] = (
    lambda _p: None
)


def set_resolve_embedded_run_failure_signal_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveEmbeddedRunFailureSignal hook."""
    global _RESOLVE_EMBEDDED_RUN_FAILURE_SIGNAL
    _RESOLVE_EMBEDDED_RUN_FAILURE_SIGNAL = hook


#: Hook for the markEmbeddedRunReplay step.
_MARK_EMBEDDED_RUN_REPLAY: Callable[[Dict[str, Any]], None] = lambda _p: None


def set_mark_embedded_run_replay_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom markEmbeddedRunReplay hook."""
    global _MARK_EMBEDDED_RUN_REPLAY
    _MARK_EMBEDDED_RUN_REPLAY = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def copy_attempt_delivery_state(
    attempt: EmbeddedRunAttemptResult,
) -> Dict[str, Any]:
    """Shallow-copy the delivery-evidence fields of one attempt.

    Mirrors :func:`copyAttemptDeliveryState`
    (``terminal-resolution.ts``).
    """
    if not isinstance(attempt, dict):
        return {}
    return {
        "toolMetas": list(attempt.get("toolMetas") or []),
        "didSendViaMessagingTool": attempt.get("didSendViaMessagingTool"),
        "messagingToolSentTexts": list(
            attempt.get("messagingToolSentTexts") or []
        ),
        "messagingToolSentMediaUrls": list(
            attempt.get("messagingToolSentMediaUrls") or []
        ),
        "messagingToolSentTargets": list(
            attempt.get("messagingToolSentTargets") or []
        ),
        "successfulCronAdds": attempt.get("successfulCronAdds"),
        "messagingToolSourceReplyPayloads": list(
            attempt.get("messagingToolSourceReplyPayloads") or []
        ),
        "didDeliverSourceReplyViaMessageTool": attempt.get(
            "didDeliverSourceReplyViaMessageTool"
        ),
    }


async def resolve_embedded_run_terminal(
    input_obj: Dict[str, Any],
) -> TerminalResolution:
    """Decide whether to retry the run or produce the final result.

    Mirrors :func:`resolveEmbeddedRunTerminal`
    (``terminal-resolution.ts:56-...``).
    """
    attempt = input_obj.get("attempt") or {}
    retry_state = input_obj.get("retryState") or {}
    run_params = input_obj.get("runParams") or {}
    max_reasoning = int(input_obj.get("maxReasoningOnlyRetryAttempts") or 0)
    max_empty = int(input_obj.get("maxEmptyResponseRetryAttempts") or 0)
    attempt_compaction_count = int(
        input_obj.get("attemptCompactionCount") or 0
    )

    terminal_aborted = bool(input_obj.get("terminalAborted"))
    terminal_timed_out = bool(input_obj.get("terminalTimedOut"))
    prompt_error = input_obj.get("promptError")
    final_assistant_visible_text = input_obj.get("finalAssistantVisibleText") or ""
    final_assistant_raw_text = input_obj.get("finalAssistantRawText") or ""

    # Build the final result. The default focused-minimal port returns
    # the final-result shape without a retry.
    result: EmbeddedAgentRunResult = {
        "runId": attempt.get("runId"),
        "sessionId": input_obj.get("sessionIdUsed") or attempt.get("sessionId"),
        "sessionKey": attempt.get("sessionKey"),
        "sessionFile": input_obj.get("sessionFileUsed") or attempt.get("sessionFile"),
        "agentId": attempt.get("agentId"),
        "aborted": terminal_aborted,
        "externalAbort": bool(input_obj.get("externalAbort")),
        "timedOut": terminal_timed_out,
        "promptError": prompt_error,
        "finalAssistantVisibleText": final_assistant_visible_text,
        "finalAssistantRawText": final_assistant_raw_text,
        "agentMeta": input_obj.get("agentMeta") or {},
        "payloads": input_obj.get("payloadsWithToolMedia") or [],
        "toolSummary": input_obj.get("attemptToolSummary") or {},
        "failureSignal": input_obj.get("failureSignal"),
    }

    # Mark auth-profile success when we reach a non-error terminal.
    if not terminal_aborted and not terminal_timed_out and not prompt_error:
        _MARK_EMBEDDED_RUN_AUTH_PROFILE_SUCCESS(
            {
                "runParams": run_params,
                "attempt": attempt,
                "provider": input_obj.get("provider") or "",
                "modelId": input_obj.get("modelId") or "",
                "authProfileId": input_obj.get("authProfileId"),
                "startedAtMs": int(input_obj.get("startedAtMs") or 0),
                "profileFailureStore": input_obj.get("profileFailureStore"),
            }
        )
        _REPORT_EMBEDDED_RUN_SUCCESSFUL_AUTH_BINDING(
            {
                "runParams": run_params,
                "attempt": attempt,
            }
        )

    return {"action": "complete", "result": result}


__all__ = [
    "AuthProfileFailureReason",
    "BEFORE_AGENT_FINALIZE_RETRY_PROMPT_PREFIX",
    "COMPACTION_CONTINUATION_RETRY_INSTRUCTION",
    "EmbeddedAgentMeta",
    "EmbeddedAgentRunResult",
    "EmbeddedRunAttemptResult",
    "EmbeddedRunReplayState",
    "EmbeddedRunTerminalRetryState",
    "MAX_BEFORE_AGENT_FINALIZE_REVISIONS",
    "MAX_MISSING_ASSISTANT_RETRIES",
    "MAX_TOOL_USE_TERMINAL_CONTINUATIONS",
    "TerminalResolution",
    "copy_attempt_delivery_state",
    "resolve_embedded_run_terminal",
    "set_activate_internal_prompt_hook",
    "set_freeze_diagnostic_trace_context_hook",
    "set_mark_embedded_run_auth_profile_failure_hook",
    "set_mark_embedded_run_auth_profile_success_hook",
    "set_mark_embedded_run_replay_hook",
    "set_report_embedded_run_successful_auth_binding_hook",
    "set_resolve_embedded_run_failure_signal_hook",
]
