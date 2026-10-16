"""jarvis.agents.tool_loop_detection — Tool-call loop detection.

Watches recent tool history for repeated no-progress patterns and circuit-breaker thresholds.
OpenClaw parity: mirrors ``openclaw-main/src/agents/tool-loop-detection.ts``.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict

_LOG = logging.getLogger("jarvis.agents.tool_loop_detection")

LoopDetectorKind = Literal[
    "generic_repeat",
    "unknown_tool_repeat",
    "known_poll_no_progress",
    "global_circuit_breaker",
    "ping_pong",
]

class LoopDetectionResultStuck(TypedDict):
    stuck: Literal[True]
    level: Literal["warning", "critical"]
    detector: LoopDetectorKind
    count: int
    message: str
    pairedToolName: Optional[str]
    warningKey: Optional[str]

class LoopDetectionResultNotStuck(TypedDict):
    stuck: Literal[False]

LoopDetectionResult = LoopDetectionResultStuck | LoopDetectionResultNotStuck

TOOL_CALL_HISTORY_SIZE = 30
WARNING_THRESHOLD = 10
UNKNOWN_TOOL_THRESHOLD = 10
CRITICAL_THRESHOLD = 20
GLOBAL_CIRCUIT_BREAKER_THRESHOLD = 30

DEFAULT_LOOP_DETECTION_CONFIG = {
    "enabled": False,
    "historySize": TOOL_CALL_HISTORY_SIZE,
    "warningThreshold": WARNING_THRESHOLD,
    "unknownToolThreshold": UNKNOWN_TOOL_THRESHOLD,
    "criticalThreshold": CRITICAL_THRESHOLD,
    "globalCircuitBreakerThreshold": GLOBAL_CIRCUIT_BREAKER_THRESHOLD,
    "detectors": {
        "genericRepeat": True,
        "knownPollNoProgress": True,
        "pingPong": True,
    },
}

class ToolCallRecord(TypedDict, total=False):
    toolName: str
    argsHash: str
    toolCallId: Optional[str]
    runId: Optional[str]
    resultHash: Optional[str]
    unknownToolName: Optional[str]
    timestamp: float


class ToolLoopDetectionScope(TypedDict, total=False):
    runId: Optional[str]


def _normalize_run_id(run_id: Any) -> Optional[str]:
    return str(run_id) if isinstance(run_id, str) and run_id else None


def _select_history_for_scope(
    history: List[ToolCallRecord], scope: Optional[ToolLoopDetectionScope] = None
) -> List[ToolCallRecord]:
    run_id = _normalize_run_id(scope.get("runId") if scope else None)
    return [
        record for record in history
        if _normalize_run_id(record.get("runId")) == run_id
    ]


def _as_positive_int(value: Any, fallback: int) -> int:
    if not isinstance(value, int) or value <= 0:
        return fallback
    return value


def resolve_loop_detection_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config or {}
    warning_threshold = _as_positive_int(
        config.get("warningThreshold"), DEFAULT_LOOP_DETECTION_CONFIG["warningThreshold"]
    )
    critical_threshold = _as_positive_int(
        config.get("criticalThreshold"), DEFAULT_LOOP_DETECTION_CONFIG["criticalThreshold"]
    )
    global_cb_threshold = _as_positive_int(
        config.get("globalCircuitBreakerThreshold"), DEFAULT_LOOP_DETECTION_CONFIG["globalCircuitBreakerThreshold"]
    )

    if critical_threshold <= warning_threshold:
        critical_threshold = warning_threshold + 1
    if global_cb_threshold <= critical_threshold:
        global_cb_threshold = critical_threshold + 1

    detectors = config.get("detectors", {})
    default_detectors = DEFAULT_LOOP_DETECTION_CONFIG["detectors"]

    return {
        "enabled": config.get("enabled", DEFAULT_LOOP_DETECTION_CONFIG["enabled"]),
        "historySize": _as_positive_int(
            config.get("historySize"), DEFAULT_LOOP_DETECTION_CONFIG["historySize"]
        ),
        "warningThreshold": warning_threshold,
        "unknownToolThreshold": _as_positive_int(
            config.get("unknownToolThreshold"), DEFAULT_LOOP_DETECTION_CONFIG["unknownToolThreshold"]
        ),
        "criticalThreshold": critical_threshold,
        "globalCircuitBreakerThreshold": global_cb_threshold,
        "detectors": {
            "genericRepeat": detectors.get("genericRepeat", default_detectors["genericRepeat"]),
            "knownPollNoProgress": detectors.get("knownPollNoProgress", default_detectors["knownPollNoProgress"]),
            "pingPong": detectors.get("pingPong", default_detectors["pingPong"]),
        },
    }


def _stable_stringify(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except Exception:
        return str(value)


def _digest_stable(value: Any) -> str:
    serialized = _stable_stringify(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _hash_tool_call(tool_name: str, params: Any) -> str:
    return f"{tool_name}:{_digest_stable(params)}"


def _is_known_poll_tool_call(tool_name: str, params: Any) -> bool:
    if tool_name == "command_status":
        return True
    if tool_name != "process" or not isinstance(params, dict):
        return False
    action = params.get("action")
    return action in ("poll", "log")


def _extract_text_content(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    content = result.get("content")
    if not isinstance(content, list):
        return ""
    texts = []
    for entry in content:
        if isinstance(entry, dict) and isinstance(entry.get("type"), str) and isinstance(entry.get("text"), str):
            texts.append(entry["text"])
    return "\n".join(texts).strip()


def _format_error_for_hash(error: Any) -> str:
    if isinstance(error, Exception):
        return str(error) or error.__class__.__name__
    if isinstance(error, (str, int, bool, float)):
        return str(error)
    return _stable_stringify(error)


def _extract_unknown_tool_name(error: Any) -> Optional[str]:
    import re
    raw = _format_error_for_hash(error).strip()
    if not raw:
        return None
    match1 = re.search(r'unknown tool[:\s]+["\']?([a-z0-9_.-]+)["\']?', raw, re.IGNORECASE)
    match2 = re.search(r'tool\s+["\']?([a-z0-9_.-]+)["\']?\s+(?:not found|is not available)', raw, re.IGNORECASE)
    match = match1 or match2
    if match and match.group(1):
        return match.group(1).strip().lower()
    return None


def _string_field(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _hash_exec_tool_outcome(details: Dict[str, Any], text: str) -> Optional[str]:
    status = _string_field(details.get("status"))
    if not status:
        return None

    if status == "running":
        return _digest_stable({
            "status": status,
            "tail": _string_field(details.get("tail")) or "",
        })

    if status in ("completed", "failed"):
        aggregated = _string_field(details.get("aggregated"))
        exit_code = details.get("exitCode")
        return _digest_stable({
            "status": status,
            "exitCode": exit_code if isinstance(exit_code, int) else None,
            "timedOut": details.get("timedOut") is True,
            "output": aggregated if aggregated else text,
        })
    return None


SEND_LIKE_MESSAGE_ACTIONS = {
    "send", "broadcast", "reply", "thread-reply",
    "sendWithEffect", "sendAttachment", "upload-file", "sticker", "poll"
}

VOLATILE_SEND_RESULT_KEYS = {
    "messageId", "message_id", "messageIds", "platformMessageId", "platformMessageIds",
    "fileId", "file_id", "fileKey", "pollId", "poll_id", "receipt", "runId",
    "idempotencyKey", "ts", "timestamp", "sentAt", "deliveredAt", "createdAt"
}


def _is_message_delivery_object(value: Dict[str, Any]) -> bool:
    return (
        isinstance(value.get("id"), str) and
        isinstance(value.get("text"), str) and
        (
            isinstance(value.get("direction"), str) or
            isinstance(value.get("senderId"), str) or
            isinstance(value.get("accountId"), str) or
            isinstance(value.get("conversation"), dict)
        )
    )


def _strip_volatile_send_ids(value: Any) -> Any:
    if isinstance(value, list):
        return [_strip_volatile_send_ids(v) for v in value]
    if not isinstance(value, dict):
        return value
    
    drop_msg_obj_id = _is_message_delivery_object(value)
    stripped = {}
    for k, v in value.items():
        if k in VOLATILE_SEND_RESULT_KEYS or (k == "id" and drop_msg_obj_id):
            continue
        stripped[k] = _strip_volatile_send_ids(v)
    return stripped


def _is_messaging_tool_send_action(tool_name: str, args: Dict[str, Any]) -> bool:
    # Stub for isMessagingToolSendAction
    return tool_name in ("telegram", "discord", "slack", "imessage", "whatsapp")


def _is_volatile_send_result(tool_name: str, params: Any) -> bool:
    if tool_name == "sessions_send":
        return True
    args = params if isinstance(params, dict) else {}
    if tool_name == "message":
        return isinstance(args.get("action"), str) and args["action"] in SEND_LIKE_MESSAGE_ACTIONS
    return _is_messaging_tool_send_action(tool_name, args)


def _is_loop_veto_result(details: Dict[str, Any]) -> bool:
    return details.get("status") == "blocked" and details.get("deniedReason") == "tool-loop"


def _hash_tool_outcome(
    tool_name: str, params: Any, result: Any, error: Any
) -> Dict[str, Any]:
    if error is not None:
        unknown_tool_name = _extract_unknown_tool_name(error)
        return {
            "resultHash": f"error:{_digest_stable(_format_error_for_hash(error))}",
            "unknownToolName": unknown_tool_name,
        }
    if not isinstance(result, dict):
        return {"resultHash": None if result is None else _digest_stable(result)}

    details = result.get("details") if isinstance(result.get("details"), dict) else {}
    text = _extract_text_content(result)

    if _is_loop_veto_result(details):
        return {"resultHash": None}

    if tool_name == "exec":
        exec_hash = _hash_exec_tool_outcome(details, text)
        if exec_hash:
            return {"resultHash": exec_hash}

    if _is_known_poll_tool_call(tool_name, params) and tool_name == "process" and isinstance(params, dict):
        action = params.get("action")
        if action == "poll":
            return {
                "resultHash": _digest_stable({
                    "action": action,
                    "status": details.get("status"),
                    "exitCode": details.get("exitCode"),
                    "exitSignal": details.get("exitSignal"),
                    "aggregated": details.get("aggregated"),
                    "text": text,
                })
            }
        if action == "log":
            return {
                "resultHash": _digest_stable({
                    "action": action,
                    "status": details.get("status"),
                    "totalLines": details.get("totalLines"),
                    "totalChars": details.get("totalChars"),
                    "truncated": details.get("truncated"),
                    "exitCode": details.get("exitCode"),
                    "exitSignal": details.get("exitSignal"),
                    "text": text,
                })
            }

    if _is_volatile_send_result(tool_name, params):
        return {"resultHash": _digest_stable(_strip_volatile_send_ids(details))}

    return {
        "resultHash": _digest_stable({
            "details": details,
            "text": text,
        })
    }


def _get_unknown_tool_repeat_streak(
    history: List[ToolCallRecord], tool_name: str
) -> Tuple[int, Optional[str]]:
    streak = 0
    repeated_unknown = None

    for i in range(len(history) - 1, -1, -1):
        record = history[i]
        if not record or record.get("toolName") != tool_name or not record.get("unknownToolName"):
            break
        if not repeated_unknown:
            repeated_unknown = record.get("unknownToolName")
            streak = 1
            continue
        if record.get("unknownToolName") != repeated_unknown:
            break
        streak += 1

    return streak, repeated_unknown


def _get_no_progress_streak(
    history: List[ToolCallRecord], tool_name: str, args_hash: str
) -> Tuple[int, Optional[str]]:
    streak = 0
    latest_result_hash = None

    for i in range(len(history) - 1, -1, -1):
        record = history[i]
        if not record or record.get("toolName") != tool_name or record.get("argsHash") != args_hash:
            continue
        res_hash = record.get("resultHash")
        if not isinstance(res_hash, str) or not res_hash:
            continue
        if not latest_result_hash:
            latest_result_hash = res_hash
            streak = 1
            continue
        if res_hash != latest_result_hash:
            break
        streak += 1

    return streak, latest_result_hash


def _get_ping_pong_streak(
    history: List[ToolCallRecord], current_signature: str
) -> Dict[str, Any]:
    if not history:
        return {"count": 0, "noProgressEvidence": False}
    last = history[-1]

    other_signature = None
    other_tool_name = None
    for i in range(len(history) - 2, -1, -1):
        call = history[i]
        if not call:
            continue
        if call.get("argsHash") != last.get("argsHash"):
            other_signature = call.get("argsHash")
            other_tool_name = call.get("toolName")
            break

    if not other_signature or not other_tool_name:
        return {"count": 0, "noProgressEvidence": False}

    alternating_tail_count = 0
    for i in range(len(history) - 1, -1, -1):
        call = history[i]
        if not call:
            continue
        expected = last.get("argsHash") if alternating_tail_count % 2 == 0 else other_signature
        if call.get("argsHash") != expected:
            break
        alternating_tail_count += 1

    if alternating_tail_count < 2:
        return {"count": 0, "noProgressEvidence": False}

    expected_current_signature = other_signature
    if current_signature != expected_current_signature:
        return {"count": 0, "noProgressEvidence": False}

    tail_start = max(0, len(history) - alternating_tail_count)
    first_hash_a = None
    first_hash_b = None
    no_progress_evidence = True
    for i in range(tail_start, len(history)):
        call = history[i]
        if not call:
            continue
        if not call.get("resultHash"):
            no_progress_evidence = False
            break
        if call.get("argsHash") == last.get("argsHash"):
            if not first_hash_a:
                first_hash_a = call.get("resultHash")
            elif first_hash_a != call.get("resultHash"):
                no_progress_evidence = False
                break
            continue
        if call.get("argsHash") == other_signature:
            if not first_hash_b:
                first_hash_b = call.get("resultHash")
            elif first_hash_b != call.get("resultHash"):
                no_progress_evidence = False
                break
            continue
        no_progress_evidence = False
        break

    if not first_hash_a or not first_hash_b:
        no_progress_evidence = False

    return {
        "count": alternating_tail_count + 1,
        "pairedToolName": last.get("toolName"),
        "pairedSignature": last.get("argsHash"),
        "noProgressEvidence": no_progress_evidence,
    }


def _canonical_pair_key(sig_a: str, sig_b: str) -> str:
    return "|".join(sorted([sig_a, sig_b]))


def detect_tool_call_loop(
    state: Dict[str, Any],
    tool_name: str,
    params: Any,
    config: Optional[Dict[str, Any]] = None,
    scope: Optional[ToolLoopDetectionScope] = None,
) -> LoopDetectionResult:
    resolved_config = resolve_loop_detection_config(config)
    if not resolved_config["enabled"]:
        return {"stuck": False}

    history = _select_history_for_scope(state.get("toolCallHistory", []), scope)
    current_hash = _hash_tool_call(tool_name, params)
    
    unknown_streak_count, unknown_name = _get_unknown_tool_repeat_streak(history, tool_name)
    no_prog_count, latest_res_hash = _get_no_progress_streak(history, tool_name, current_hash)
    
    known_poll = _is_known_poll_tool_call(tool_name, params)
    ping_pong = _get_ping_pong_streak(history, current_hash)

    if unknown_streak_count >= resolved_config["unknownToolThreshold"]:
        used_name = unknown_name or tool_name
        return {
            "stuck": True,
            "level": "critical",
            "detector": "unknown_tool_repeat",
            "count": unknown_streak_count,
            "message": f"CRITICAL: attempted unavailable tool {used_name} {unknown_streak_count} times. Stop retrying that missing tool and answer without it.",
            "pairedToolName": None,
            "warningKey": f"unknown-tool:{tool_name}:{unknown_name or 'unknown'}",
        }

    if no_prog_count >= resolved_config["globalCircuitBreakerThreshold"]:
        _LOG.error(f"Global circuit breaker triggered: {tool_name} repeated {no_prog_count} times with no progress")
        return {
            "stuck": True,
            "level": "critical",
            "detector": "global_circuit_breaker",
            "count": no_prog_count,
            "message": f"CRITICAL: {tool_name} has repeated identical no-progress outcomes {no_prog_count} times. Session execution blocked by global circuit breaker to prevent runaway loops.",
            "pairedToolName": None,
            "warningKey": f"global:{tool_name}:{current_hash}:{latest_res_hash or 'none'}",
        }

    if known_poll and resolved_config["detectors"]["knownPollNoProgress"] and no_prog_count >= resolved_config["criticalThreshold"]:
        _LOG.error(f"Critical polling loop detected: {tool_name} repeated {no_prog_count} times")
        return {
            "stuck": True,
            "level": "critical",
            "detector": "known_poll_no_progress",
            "count": no_prog_count,
            "message": f"CRITICAL: Called {tool_name} with identical arguments and no progress {no_prog_count} times. This appears to be a stuck polling loop. Session execution blocked to prevent resource waste.",
            "pairedToolName": None,
            "warningKey": f"poll:{tool_name}:{current_hash}:{latest_res_hash or 'none'}",
        }

    if known_poll and resolved_config["detectors"]["knownPollNoProgress"] and no_prog_count >= resolved_config["warningThreshold"]:
        _LOG.warning(f"Polling loop warning: {tool_name} repeated {no_prog_count} times")
        return {
            "stuck": True,
            "level": "warning",
            "detector": "known_poll_no_progress",
            "count": no_prog_count,
            "message": f"WARNING: You have called {tool_name} {no_prog_count} times with identical arguments and no progress. Stop polling and either (1) increase wait time between checks, or (2) report the task as failed if the process is stuck.",
            "pairedToolName": None,
            "warningKey": f"poll:{tool_name}:{current_hash}:{latest_res_hash or 'none'}",
        }

    ping_pong_key = (
        f"pingpong:{_canonical_pair_key(current_hash, ping_pong['pairedSignature'])}"
        if ping_pong.get("pairedSignature") else f"pingpong:{tool_name}:{current_hash}"
    )

    if resolved_config["detectors"]["pingPong"] and ping_pong["count"] >= resolved_config["criticalThreshold"] and ping_pong["noProgressEvidence"]:
        _LOG.error(f"Critical ping-pong loop detected: alternating calls count={ping_pong['count']} currentTool={tool_name}")
        return {
            "stuck": True,
            "level": "critical",
            "detector": "ping_pong",
            "count": ping_pong["count"],
            "message": f"CRITICAL: You are alternating between repeated tool-call patterns ({ping_pong['count']} consecutive calls) with no progress. This appears to be a stuck ping-pong loop. Session execution blocked to prevent resource waste.",
            "pairedToolName": ping_pong.get("pairedToolName"),
            "warningKey": ping_pong_key,
        }

    if resolved_config["detectors"]["pingPong"] and ping_pong["count"] >= resolved_config["warningThreshold"]:
        _LOG.warning(f"Ping-pong loop warning: alternating calls count={ping_pong['count']} currentTool={tool_name}")
        return {
            "stuck": True,
            "level": "warning",
            "detector": "ping_pong",
            "count": ping_pong["count"],
            "message": f"WARNING: You are alternating between repeated tool-call patterns ({ping_pong['count']} consecutive calls). This looks like a ping-pong loop; stop retrying and report the task as failed.",
            "pairedToolName": ping_pong.get("pairedToolName"),
            "warningKey": ping_pong_key,
        }

    recent_count = sum(
        1 for h in history if h.get("toolName") == tool_name and h.get("argsHash") == current_hash
    )

    if not known_poll and resolved_config["detectors"]["genericRepeat"] and no_prog_count >= resolved_config["criticalThreshold"]:
        _LOG.error(f"Critical generic loop detected: {tool_name} repeated {no_prog_count} times")
        return {
            "stuck": True,
            "level": "critical",
            "detector": "generic_repeat",
            "count": no_prog_count,
            "message": f"CRITICAL: Called {tool_name} with identical arguments and identical outcomes {no_prog_count} times. Session execution blocked to prevent runaway loops.",
            "pairedToolName": None,
            "warningKey": f"generic:{tool_name}:{current_hash}:{latest_res_hash or 'none'}",
        }

    if not known_poll and resolved_config["detectors"]["genericRepeat"] and recent_count >= resolved_config["warningThreshold"]:
        _LOG.warning(f"Loop warning: {tool_name} called {recent_count} times with identical arguments")
        return {
            "stuck": True,
            "level": "warning",
            "detector": "generic_repeat",
            "count": recent_count,
            "message": f"WARNING: You have called {tool_name} {recent_count} times with identical arguments. If this is not making progress, stop retrying and report the task as failed.",
            "pairedToolName": None,
            "warningKey": f"generic:{tool_name}:{current_hash}",
        }

    return {"stuck": False}


def record_tool_call(
    state: Dict[str, Any],
    tool_name: str,
    params: Any,
    tool_call_id: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    scope: Optional[ToolLoopDetectionScope] = None,
) -> None:
    resolved_config = resolve_loop_detection_config(config)
    run_id = _normalize_run_id(scope.get("runId") if scope else None)
    
    if "toolCallHistory" not in state:
        state["toolCallHistory"] = []

    import time
    record: ToolCallRecord = {
        "toolName": tool_name,
        "argsHash": _hash_tool_call(tool_name, params),
        "toolCallId": tool_call_id,
        "timestamp": time.time() * 1000,
    }
    if run_id:
        record["runId"] = run_id

    state["toolCallHistory"].append(record)

    history_size = resolved_config["historySize"]
    if len(state["toolCallHistory"]) > history_size:
        state["toolCallHistory"] = state["toolCallHistory"][-history_size:]


def record_tool_call_outcome(
    state: Dict[str, Any],
    params: Dict[str, Any],
) -> Optional[ToolCallRecord]:
    resolved_config = resolve_loop_detection_config(params.get("config"))
    run_id = _normalize_run_id(params.get("runId"))
    
    outcome = _hash_tool_outcome(
        params.get("toolName", ""), params.get("toolParams"), params.get("result"), params.get("error")
    )
    result_hash = outcome.get("resultHash")
    if not result_hash:
        return None

    if "toolCallHistory" not in state:
        state["toolCallHistory"] = []

    args_hash = _hash_tool_call(params.get("toolName", ""), params.get("toolParams"))
    matched = False
    recorded_outcome = None
    
    for i in range(len(state["toolCallHistory"]) - 1, -1, -1):
        call = state["toolCallHistory"][i]
        if not call:
            continue
        if _normalize_run_id(call.get("runId")) != run_id:
            continue
        if params.get("toolCallId") and call.get("toolCallId") != params.get("toolCallId"):
            continue
        if call.get("toolName") != params.get("toolName") or call.get("argsHash") != args_hash:
            continue
        if call.get("resultHash") is not None:
            continue
        
        call["resultHash"] = result_hash
        call["unknownToolName"] = outcome.get("unknownToolName")
        matched = True
        recorded_outcome = call
        break

    if not matched:
        import time
        record: ToolCallRecord = {
            "toolName": params.get("toolName", ""),
            "argsHash": args_hash,
            "toolCallId": params.get("toolCallId"),
            "resultHash": result_hash,
            "unknownToolName": outcome.get("unknownToolName"),
            "timestamp": time.time() * 1000,
        }
        if run_id:
            record["runId"] = run_id
        state["toolCallHistory"].append(record)
        recorded_outcome = record

    history_size = resolved_config["historySize"]
    if len(state["toolCallHistory"]) > history_size:
        state["toolCallHistory"] = state["toolCallHistory"][-history_size:]
        
    return recorded_outcome


__all__ = [
    "LoopDetectorKind",
    "LoopDetectionResult",
    "ToolCallRecord",
    "ToolLoopDetectionScope",
    "resolve_loop_detection_config",
    "detect_tool_call_loop",
    "record_tool_call",
    "record_tool_call_outcome",
    "UNKNOWN_TOOL_THRESHOLD",
]
