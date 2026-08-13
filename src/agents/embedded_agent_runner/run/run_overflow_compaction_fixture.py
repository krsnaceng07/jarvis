"""jarvis.agents.embedded_agent_runner.run.run_overflow_compaction_fixture — overflow compaction test fixtures.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run.overflow-compaction.fixture.ts``.

Phase 7.6h-6 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.agents.tool_replay_safety import is_agent_tool_replay_safe

from .incomplete_turn import build_attempt_replay_metadata

ContextEngineSessionTarget = Dict[str, Any]

DEFAULT_OVERFLOW_ERROR_MESSAGE = (
    "request_too_large: Request size exceeds model context window"
)


def make_overflow_error(message: str = DEFAULT_OVERFLOW_ERROR_MESSAGE) -> Exception:
    return Exception(message)


def make_compaction_success(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "ok": True,
        "compacted": True,
        "result": {
            "summary": params["summary"],
            **(
                {"firstKeptEntryId": params["firstKeptEntryId"]}
                if params.get("firstKeptEntryId") is not None
                else {}
            ),
            **(
                {"tokensBefore": params["tokensBefore"]}
                if params.get("tokensBefore") is not None
                else {}
            ),
            **(
                {"tokensAfter": params["tokensAfter"]}
                if params.get("tokensAfter") is not None
                else {}
            ),
            **(
                {"sessionId": params["sessionId"]}
                if params.get("sessionId") is not None
                else {}
            ),
            **(
                {"sessionFile": params["sessionFile"]}
                if params.get("sessionFile") is not None
                else {}
            ),
            **(
                {"sessionTarget": params["sessionTarget"]}
                if params.get("sessionTarget") is not None
                else {}
            ),
        },
    }


def make_attempt_result(
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    overrides = overrides or {}
    tool_metas: List[Dict[str, Any]] = []
    for entry in overrides.get("toolMetas", []):
        if not isinstance(entry, dict):
            tool_metas.append(entry)
            continue
        replay_safe = (
            entry["replaySafe"]
            if "replaySafe" in entry
            else is_agent_tool_replay_safe({"name": entry.get("toolName")})
        )
        tool_metas.append({**entry, "replaySafe": replay_safe})

    did_send_via_messaging_tool = overrides.get("didSendViaMessagingTool", False)
    messaging_tool_sent_texts = overrides.get("messagingToolSentTexts", [])
    messaging_tool_sent_media_urls = overrides.get("messagingToolSentMediaUrls", [])
    messaging_tool_sent_targets = overrides.get("messagingToolSentTargets", [])
    successful_cron_adds = overrides.get("successfulCronAdds")
    accepted_session_spawns = overrides.get("acceptedSessionSpawns", [])

    result: Dict[str, Any] = {
        "aborted": False,
        "externalAbort": False,
        "timedOut": False,
        "idleTimedOut": False,
        "timedOutDuringCompaction": False,
        "timedOutDuringToolExecution": False,
        "promptError": None,
        "promptErrorSource": None,
        "sessionIdUsed": "test-session",
        "assistantTexts": ["Hello!"],
        "acceptedSessionSpawns": accepted_session_spawns,
        "lastAssistant": None,
        "currentAttemptCompletedAssistant": overrides.get(
            "currentAttemptCompletedAssistant",
            overrides.get("currentAttemptAssistant"),
        ),
        "messagesSnapshot": [],
        "replayMetadata": build_attempt_replay_metadata(
            {
                "toolMetas": tool_metas,
                "didSendViaMessagingTool": did_send_via_messaging_tool,
                "messagingToolSentTexts": messaging_tool_sent_texts,
                "messagingToolSentMediaUrls": messaging_tool_sent_media_urls,
                "messagingToolSentTargets": messaging_tool_sent_targets,
                "acceptedSessionSpawns": accepted_session_spawns,
                "successfulCronAdds": successful_cron_adds,
            }
        ),
        "itemLifecycle": {
            "startedCount": 0,
            "completedCount": 0,
            "activeCount": 0,
        },
        "didSendViaMessagingTool": did_send_via_messaging_tool,
        "messagingToolSentTexts": messaging_tool_sent_texts,
        "messagingToolSentMediaUrls": messaging_tool_sent_media_urls,
        "messagingToolSentTargets": messaging_tool_sent_targets,
        "cloudCodeAssistFormatError": False,
        "toolMetas": tool_metas,
    }
    result.update({k: v for k, v in overrides.items() if k != "toolMetas"})
    result["toolMetas"] = tool_metas
    return result


def mock_overflow_retry_success(
    run_embedded_attempt: Any,
    compact_direct: Any,
    overflow_message: Optional[str] = None,
) -> Exception:
    overflow_error = make_overflow_error(
        overflow_message or DEFAULT_OVERFLOW_ERROR_MESSAGE,
    )
    run_embedded_attempt.mock_resolved_value_once(
        make_attempt_result({"promptError": overflow_error}),
    )
    run_embedded_attempt.mock_resolved_value_once(
        make_attempt_result({"promptError": None}),
    )
    compact_direct.mock_resolved_value_once(
        make_compaction_success(
            {
                "summary": "Compacted session",
                "firstKeptEntryId": "entry-5",
                "tokensBefore": 150000,
            }
        )
    )
    return overflow_error


def queue_overflow_attempt_with_oversized_tool_output(
    run_embedded_attempt: Any,
    overflow_error: Optional[Exception] = None,
) -> Exception:
    overflow_error = overflow_error or make_overflow_error()
    run_embedded_attempt.mock_resolved_value_once(
        make_attempt_result(
            {
                "promptError": overflow_error,
                "messagesSnapshot": [
                    {
                        "role": "toolResult",
                        "content": [
                            {
                                "type": "text",
                                "text": "x" * 80_000,
                            }
                        ],
                    }
                ],
            }
        )
    )
    return overflow_error


__all__ = [
    "ContextEngineSessionTarget",
    "DEFAULT_OVERFLOW_ERROR_MESSAGE",
    "is_agent_tool_replay_safe",
    "make_overflow_error",
    "make_compaction_success",
    "make_attempt_result",
    "mock_overflow_retry_success",
    "queue_overflow_attempt_with_oversized_tool_output",
]
