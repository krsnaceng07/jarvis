"""jarvis.agents.embedded_agent_runner.result_fallback_classifier — classify results for fallback.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/result-fallback-classifier.ts``.

Public surface:

- :func:`classify_embedded_agent_run_result_for_model_fallback`
- :func:`merge_embedded_agent_run_result_for_model_fallback_exhaustion`
- :func:`has_deliberate_silent_terminal_reply`

Phase 7.6h-4 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


#: Generic external-run failure text marker.
GENERIC_EXTERNAL_RUN_FAILURE_TEXT = "Sorry, I couldn't complete that request."


# Installable hooks ---------------------------------------------------------

_classify_embedded_agent_run_result_for_model_fallback_hook = None
_merge_embedded_agent_run_result_for_model_fallback_exhaustion_hook = None
_has_deliberate_silent_terminal_reply_hook = None


def set_classify_embedded_agent_run_result_for_model_fallback_hook(fn) -> None:
    global _classify_embedded_agent_run_result_for_model_fallback_hook
    _classify_embedded_agent_run_result_for_model_fallback_hook = fn


def set_merge_embedded_agent_run_result_for_model_fallback_exhaustion_hook(fn) -> None:
    global _merge_embedded_agent_run_result_for_model_fallback_exhaustion_hook
    _merge_embedded_agent_run_result_for_model_fallback_exhaustion_hook = fn


def set_has_deliberate_silent_terminal_reply_hook(fn) -> None:
    global _has_deliberate_silent_terminal_reply_hook
    _has_deliberate_silent_terminal_reply_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def has_deliberate_silent_terminal_reply(result: Dict[str, Any]) -> bool:
    """Whether the terminal result is a deliberate silent reply.

    Mirrors :func:`hasDeliberateSilentTerminalReply`
    (``result-fallback-classifier.ts``).
    """
    if _has_deliberate_silent_terminal_reply_hook is not None:
        return bool(_has_deliberate_silent_terminal_reply_hook(result))
    if not isinstance(result, dict):
        return False
    meta = result.get("meta") or {}
    if not isinstance(meta, dict):
        return False
    error = meta.get("error")
    if isinstance(error, dict) and error.get("kind") == "hook_block":
        return True
    for key in ("finalAssistantRawText", "finalAssistantVisibleText"):
        text = meta.get(key)
        if isinstance(text, str):
            if _is_silent_reply_payload_text(text):
                return True
    return False


def merge_embedded_agent_run_result_for_model_fallback_exhaustion(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge a preferred result onto the latest result for fallback exhaustion bookkeeping.

    Mirrors :func:`mergeEmbeddedAgentRunResultForModelFallbackExhaustion`
    (``result-fallback-classifier.ts``).
    """
    if _merge_embedded_agent_run_result_for_model_fallback_exhaustion_hook is not None:
        return (
            _merge_embedded_agent_run_result_for_model_fallback_exhaustion_hook(params)
            or params.get("latestResult", {})
        )
    latest = params.get("latestResult") or {}
    preferred = params.get("preferredResult") or {}
    if latest is preferred:
        return latest
    return {
        **latest,
        "payloads": preferred.get("payloads"),
        "meta": {
            **(latest.get("meta") or {}),
            "error": (preferred.get("meta") or {}).get("error"),
        },
    }


def classify_embedded_agent_run_result_for_model_fallback(
    params: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Return a fallback classification when the embedded run failed invisibly.

    Mirrors :func:`classifyEmbeddedAgentRunResultForModelFallback`
    (``result-fallback-classifier.ts``).
    """
    if _classify_embedded_agent_run_result_for_model_fallback_hook is not None:
        return _classify_embedded_agent_run_result_for_model_fallback_hook(params)
    result = params.get("result")
    if not _is_embedded_agent_run_result(result):
        return None
    meta = (result or {}).get("meta") or {}
    if meta.get("aborted") or params.get("hasDirectlySentBlockReply") or params.get("hasBlockReplyPipelineOutput"):
        return None
    if meta.get("error", {}).get("kind") == "hook_block":
        return None
    if _has_visible_text(meta):
        return None
    payloads = result.get("payloads") or []
    generic = _classify_generic_external_run_failure_payload(
        params.get("provider", ""), params.get("model", ""), result
    )
    if generic:
        return generic
    harness = _classify_harness_result(params.get("provider", ""), params.get("model", ""), meta)
    if harness:
        return harness
    if not payloads:
        return {
            "message": f"{params.get('provider', '')}/{params.get('model', '')} ended without a visible assistant reply",
            "reason": "format",
            "code": "empty_result",
        }
    if all((p.get("isReasoning") is True) for p in payloads if isinstance(p, dict)):
        return {
            "message": f"{params.get('provider', '')}/{params.get('model', '')} ended with reasoning only",
            "reason": "format",
            "code": "reasoning_only_result",
        }
    return None


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _is_embedded_agent_run_result(value: Any) -> bool:
    return bool(
        value
        and isinstance(value, dict)
        and "meta" in value
        and isinstance(value.get("meta"), dict)
    )


def _is_silent_reply_payload_text(text: str) -> bool:
    return text.strip() in ("", "(no reply)")


def _has_visible_text(meta: Dict[str, Any]) -> bool:
    text = meta.get("finalAssistantVisibleText")
    if not isinstance(text, str):
        return False
    return bool(text.strip()) and not _is_silent_reply_payload_text(text)


def _classify_generic_external_run_failure_payload(
    provider: str,
    model: str,
    result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    payloads = result.get("payloads")
    if not isinstance(payloads, list) or len(payloads) != 1:
        return None
    payload = payloads[0]
    if not isinstance(payload, dict):
        return None
    text = payload.get("text")
    if payload.get("isError") or payload.get("isReasoning") or not isinstance(text, str):
        return None
    if text.strip() != GENERIC_EXTERNAL_RUN_FAILURE_TEXT:
        return None
    return {
        "message": f"{provider}/{model} ended with a generic external runner failure: {text}",
        "reason": "format",
        "code": "generic_external_run_failure",
        "rawError": text,
    }


def _classify_harness_result(
    provider: str, model: str, meta: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    classification = meta.get("agentHarnessResultClassification")
    if classification == "empty":
        return {
            "message": f"{provider}/{model} ended without a visible assistant reply",
            "reason": "format",
            "code": "empty_result",
        }
    if classification == "reasoning-only":
        return {
            "message": f"{provider}/{model} ended with reasoning only",
            "reason": "format",
            "code": "reasoning_only_result",
        }
    if classification == "planning-only":
        return {
            "message": f"{provider}/{model} ended with a structured plan but no final answer",
            "reason": "format",
            "code": "planning_only_result",
        }
    return None


__all__ = [
    "GENERIC_EXTERNAL_RUN_FAILURE_TEXT",
    "classify_embedded_agent_run_result_for_model_fallback",
    "merge_embedded_agent_run_result_for_model_fallback_exhaustion",
    "has_deliberate_silent_terminal_reply",
    "set_classify_embedded_agent_run_result_for_model_fallback_hook",
    "set_merge_embedded_agent_run_result_for_model_fallback_exhaustion_hook",
    "set_has_deliberate_silent_terminal_reply_hook",
]
