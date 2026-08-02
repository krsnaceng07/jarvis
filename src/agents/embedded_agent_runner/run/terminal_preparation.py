"""jarvis.agents.embedded_agent_runner.run.terminal_preparation — prepare the embedded-run terminal result.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/terminal-preparation.ts``.

Public surface:

- :func:`prepare_embedded_run_terminal` — project the attempt into the
  terminal-result shape (agent meta, payloads, assistant text, etc.).

Phase 7.6b-3 — focused minimal port.

The OpenClaw source is tightly coupled to the
reply-payload / assistant-message / failure-signal / usage-accumulator
/ tool-media-payloads / run-attempt-result layers. The Python port
keeps the public surface and delegates the heavy payload-building
and meta-resolution to installable hooks.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


#: Agent meta shape. Mirrors :class:`EmbeddedAgentMeta` from
#: ``types.ts``.
EmbeddedAgentMeta = Dict[str, Any]


#: Run result shape. Mirrors :class:`EmbeddedAgentRunResult` from
#: ``types.ts``.
EmbeddedAgentRunResult = Dict[str, Any]


#: Attempt result shape.
EmbeddedRunAttemptResult = Dict[str, Any]


#: Context-recovery state shape.
EmbeddedRunContextRecoveryState = Dict[str, Any]


#: Auth profile store shape.
AuthProfileStore = Dict[str, Any]


#: Usage accumulator shape.
UsageAccumulator = Dict[str, Any]


#: Normalized usage shape.
NormalizedUsage = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for :func:`buildEmbeddedRunPayloads` from ``payloads.py``.
_BUILD_EMBEDDED_RUN_PAYLOADS: Callable[[Dict[str, Any]], List[Dict[str, Any]]] = (
    lambda _p: []
)


def set_build_embedded_run_payloads_hook(
    hook: Callable[[Dict[str, Any]], List[Dict[str, Any]]],
) -> None:
    """Install a custom buildEmbeddedRunPayloads hook."""
    global _BUILD_EMBEDDED_RUN_PAYLOADS
    _BUILD_EMBEDDED_RUN_PAYLOADS = hook


#: Hook for :func:`mergeAttemptToolMediaPayloads` from
#: ``tool-media-payloads.ts``.
_MERGE_ATTEMPT_TOOL_MEDIA_PAYLOADS: Callable[
    [List[Dict[str, Any]], Any], List[Dict[str, Any]]
] = lambda payloads, _attempt: list(payloads or [])


def set_merge_attempt_tool_media_payloads_hook(
    hook: Callable[[List[Dict[str, Any]], Any], List[Dict[str, Any]]],
) -> None:
    """Install a custom mergeAttemptToolMediaPayloads hook."""
    global _MERGE_ATTEMPT_TOOL_MEDIA_PAYLOADS
    _MERGE_ATTEMPT_TOOL_MEDIA_PAYLOADS = hook


#: Hook for the build-usage-agent-meta-fields step.
_BUILD_USAGE_AGENT_META_FIELDS: Callable[[Dict[str, Any]], Dict[str, Any]] = (
    lambda _p: {}
)


def set_build_usage_agent_meta_fields_hook(
    hook: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> None:
    """Install a custom buildUsageAgentMetaFields hook."""
    global _BUILD_USAGE_AGENT_META_FIELDS
    _BUILD_USAGE_AGENT_META_FIELDS = hook


#: Hook for :func:`resolveFinalAssistantVisibleText` from ``helpers.ts``.
_RESOLVE_FINAL_ASSISTANT_VISIBLE_TEXT: Callable[[Dict[str, Any]], Optional[str]] = (
    lambda _p: None
)


def set_resolve_final_assistant_visible_text_hook(
    hook: Callable[[Dict[str, Any]], Optional[str]],
) -> None:
    """Install a custom resolveFinalAssistantVisibleText hook."""
    global _RESOLVE_FINAL_ASSISTANT_VISIBLE_TEXT
    _RESOLVE_FINAL_ASSISTANT_VISIBLE_TEXT = hook


#: Hook for :func:`resolveFinalAssistantRawText` from ``helpers.ts``.
_RESOLVE_FINAL_ASSISTANT_RAW_TEXT: Callable[[Dict[str, Any]], Optional[str]] = (
    lambda _p: None
)


def set_resolve_final_assistant_raw_text_hook(
    hook: Callable[[Dict[str, Any]], Optional[str]],
) -> None:
    """Install a custom resolveFinalAssistantRawText hook."""
    global _RESOLVE_FINAL_ASSISTANT_RAW_TEXT
    _RESOLVE_FINAL_ASSISTANT_RAW_TEXT = hook


#: Hook for :func:`resolveReportedModelRef` from ``helpers.ts``.
_RESOLVE_REPORTED_MODEL_REF: Callable[
    [Dict[str, Any]], Dict[str, str]
] = lambda p: {
    "provider": (p.get("provider") or ""),
    "model": (p.get("model") or ""),
}


def set_resolve_reported_model_ref_hook(
    hook: Callable[[Dict[str, Any]], Dict[str, str]],
) -> None:
    """Install a custom resolveReportedModelRef hook."""
    global _RESOLVE_REPORTED_MODEL_REF
    _RESOLVE_REPORTED_MODEL_REF = hook


#: Hook for :func:`buildTraceToolSummary` from ``run-attempt-result.ts``.
_BUILD_TRACE_TOOL_SUMMARY: Callable[[Any], Any] = lambda _attempt: {}


def set_build_trace_tool_summary_hook(
    hook: Callable[[Any], Any],
) -> None:
    """Install a custom buildTraceToolSummary hook."""
    global _BUILD_TRACE_TOOL_SUMMARY
    _BUILD_TRACE_TOOL_SUMMARY = hook


#: Hook for :func:`resolveEmbeddedRunFailureSignal` from
#: ``failure-signal.ts``.
_RESOLVE_EMBEDDED_RUN_FAILURE_SIGNAL: Callable[[Dict[str, Any]], Any] = (
    lambda _p: None
)


def set_resolve_embedded_run_failure_signal_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveEmbeddedRunFailureSignal hook."""
    global _RESOLVE_EMBEDDED_RUN_FAILURE_SIGNAL
    _RESOLVE_EMBEDDED_RUN_FAILURE_SIGNAL = hook


#: Hook for :func:`copyReplyPayloadMetadata` from
#: ``auto-reply/reply-payload.ts``.
_COPY_REPLY_PAYLOAD_METADATA: Callable[
    [Any, Any], Any
] = lambda _payload, _metadata: None


def set_copy_reply_payload_metadata_hook(
    hook: Callable[[Any, Any], Any],
) -> None:
    """Install a custom copyReplyPayloadMetadata hook."""
    global _COPY_REPLY_PAYLOAD_METADATA
    _COPY_REPLY_PAYLOAD_METADATA = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prepare_embedded_run_terminal(
    input_obj: Dict[str, Any],
) -> Dict[str, Any]:
    """Project the attempt into the terminal-result shape.

    Mirrors :func:`prepareEmbeddedRunTerminal`
    (``terminal-preparation.ts:21-...``).
    """
    attempt = input_obj.get("attempt") or {}
    run_params = input_obj.get("runParams") or {}
    timed_out_during_prompt = bool(
        input_obj.get("terminalTimedOut")
        and not input_obj.get("timedOutDuringCompaction")
        and not input_obj.get("timedOutDuringToolExecution")
    )

    final_assistant_visible_text = _RESOLVE_FINAL_ASSISTANT_VISIBLE_TEXT(
        {
            "runParams": run_params,
            "attempt": attempt,
            "currentAttemptCompletedAssistant": input_obj.get(
                "currentAttemptCompletedAssistant"
            ),
            "resolvedToolResultFormat": input_obj.get("resolvedToolResultFormat"),
        }
    )
    final_assistant_raw_text = _RESOLVE_FINAL_ASSISTANT_RAW_TEXT(
        {
            "runParams": run_params,
            "attempt": attempt,
        }
    )
    reported_model_ref = _RESOLVE_REPORTED_MODEL_REF(
        {
            "provider": input_obj.get("provider") or "",
            "model": input_obj.get("model") or "",
            "attempt": attempt,
        }
    )
    usage_meta = _BUILD_USAGE_AGENT_META_FIELDS(
        {
            "runParams": run_params,
            "usageAccumulator": input_obj.get("usageAccumulator"),
            "lastRunPromptUsage": input_obj.get("lastRunPromptUsage"),
            "lastTurnTotal": input_obj.get("lastTurnTotal"),
            "outerContextTokenMeta": input_obj.get("outerContextTokenMeta"),
        }
    )
    payloads = _BUILD_EMBEDDED_RUN_PAYLOADS(
        {
            "runParams": run_params,
            "attempt": attempt,
            "finalAssistantVisibleText": final_assistant_visible_text,
            "finalAssistantRawText": final_assistant_raw_text,
        }
    )
    payloads_with_tool_media = _MERGE_ATTEMPT_TOOL_MEDIA_PAYLOADS(payloads, attempt)
    attempt_tool_summary = _BUILD_TRACE_TOOL_SUMMARY(attempt)
    failure_signal = _RESOLVE_EMBEDDED_RUN_FAILURE_SIGNAL(
        {
            "runParams": run_params,
            "attempt": attempt,
            "terminalInterrupted": bool(input_obj.get("terminalInterrupted")),
            "terminalTimedOut": bool(input_obj.get("terminalTimedOut")),
        }
    )

    agent_meta: EmbeddedAgentMeta = {
        "provider": input_obj.get("provider") or "",
        "model": input_obj.get("model") or "",
        "modelRef": reported_model_ref,
        "sessionId": input_obj.get("sessionIdUsed") or attempt.get("sessionId"),
        "sessionFile": input_obj.get("sessionFileUsed") or attempt.get("sessionFile"),
        "authProfileId": input_obj.get("authProfileId"),
        **usage_meta,
    }
    return {
        "agentMeta": agent_meta,
        "reportedModelRef": reported_model_ref,
        "finalAssistantVisibleText": final_assistant_visible_text,
        "finalAssistantRawText": final_assistant_raw_text,
        "payloads": payloads,
        "payloadsWithToolMedia": payloads_with_tool_media,
        "timedOutDuringPrompt": timed_out_during_prompt,
        "recoveredFinalAssistantPayloadsAfterPromptTimeout": [],
        "hasSuccessfulFinalAssistantAfterPromptTimeout": False,
        "hasPartialAssistantTextAfterPromptTimeout": bool(
            (final_assistant_visible_text or "").strip()
        ),
        "attemptToolSummary": attempt_tool_summary,
        "failureSignal": failure_signal,
    }


__all__ = [
    "AuthProfileStore",
    "EmbeddedAgentMeta",
    "EmbeddedAgentRunResult",
    "EmbeddedRunAttemptResult",
    "EmbeddedRunContextRecoveryState",
    "NormalizedUsage",
    "UsageAccumulator",
    "prepare_embedded_run_terminal",
    "set_build_embedded_run_payloads_hook",
    "set_build_trace_tool_summary_hook",
    "set_build_usage_agent_meta_fields_hook",
    "set_copy_reply_payload_metadata_hook",
    "set_merge_attempt_tool_media_payloads_hook",
    "set_resolve_embedded_run_failure_signal_hook",
    "set_resolve_final_assistant_raw_text_hook",
    "set_resolve_final_assistant_visible_text_hook",
    "set_resolve_reported_model_ref_hook",
]
