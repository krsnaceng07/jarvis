"""jarvis.logging.message_lifecycle — message queue + processing diagnostic helpers.

OpenClaw parity: mirrors
``openclaw-main/src/logging/message-lifecycle.ts``.

Public surface:

- :func:`create_diagnostic_message_lifecycle`
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional


_log_message_queued: Optional[Callable[[Dict[str, Any]], None]] = None
_log_session_state_change: Optional[Callable[[Dict[str, Any]], None]] = None
_log_message_processed: Optional[Callable[[Dict[str, Any]], None]] = None


def set_log_message_queued_hook(fn) -> None:
    global _log_message_queued
    _log_message_queued = fn


def set_log_session_state_change_hook(fn) -> None:
    global _log_session_state_change
    _log_session_state_change = fn


def set_log_message_processed_hook(fn) -> None:
    global _log_message_processed
    _log_message_processed = fn


def _emit_queued(payload: Dict[str, Any]) -> None:
    if _log_message_queued is not None:
        try:
            _log_message_queued(payload)
        except Exception:
            pass


def _emit_state(payload: Dict[str, Any]) -> None:
    if _log_session_state_change is not None:
        try:
            _log_session_state_change(payload)
        except Exception:
            pass


def _emit_processed(payload: Dict[str, Any]) -> None:
    if _log_message_processed is not None:
        try:
            _log_message_processed(payload)
        except Exception:
            pass


def create_diagnostic_message_lifecycle(params: Dict[str, Any]) -> Dict[str, Any]:
    """Build a small object that emits queue + processing diagnostic events.

    Mirrors :func:`createDiagnosticMessageLifecycle`
    (``logging/message-lifecycle.ts``).
    """
    started_at_ms = params.get("startedAtMs") or int(time.time() * 1000)
    track_session_state = bool(params.get("trackSessionState", False))
    enabled = bool(params.get("enabled", False))
    base_session_id = params.get("sessionId")
    base_session_key = params.get("sessionKey")

    def _resolve_ref(override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if override:
            return {
                "sessionId": override.get("sessionId", base_session_id),
                "sessionKey": override.get("sessionKey", base_session_key),
            }
        return {"sessionId": base_session_id, "sessionKey": base_session_key}

    def _has_session_ref(ref: Dict[str, Any]) -> bool:
        return bool(ref.get("sessionId") or ref.get("sessionKey"))

    def _can_track(ref: Dict[str, Any]) -> bool:
        return enabled and track_session_state and _has_session_ref(ref)

    def mark_processing(override: Optional[Dict[str, Any]] = None) -> None:
        ref = _resolve_ref(override)
        if not _can_track(ref):
            return
        _emit_queued(
            {
                "sessionId": ref.get("sessionId"),
                "sessionKey": ref.get("sessionKey"),
                "channel": params.get("channel"),
                "source": params.get("source"),
            }
        )
        _emit_state(
            {
                "sessionId": ref.get("sessionId"),
                "sessionKey": ref.get("sessionKey"),
                "state": "processing",
                "reason": params.get("processingReason"),
            }
        )

    def mark_idle(reason: Optional[str] = None, override: Optional[Dict[str, Any]] = None) -> None:
        ref = _resolve_ref(override)
        if not _can_track(ref):
            return
        _emit_state(
            {
                "sessionId": ref.get("sessionId"),
                "sessionKey": ref.get("sessionKey"),
                "state": "idle",
                "reason": reason,
            }
        )

    def mark_processed(
        outcome: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not enabled:
            return
        ref = _resolve_ref(options)
        duration_ms = (options or {}).get("durationMs") or (int(time.time() * 1000) - started_at_ms)
        _emit_processed(
            {
                "channel": params.get("channel"),
                "chatId": params.get("chatId"),
                "messageId": params.get("messageId"),
                "sessionId": ref.get("sessionId"),
                "sessionKey": ref.get("sessionKey"),
                "durationMs": duration_ms,
                "outcome": outcome,
                "reason": (options or {}).get("reason"),
                "error": (options or {}).get("error"),
            }
        )

    return {
        "markProcessing": mark_processing,
        "markIdle": mark_idle,
        "markProcessed": mark_processed,
    }


__all__ = [
    "create_diagnostic_message_lifecycle",
    "set_log_message_queued_hook",
    "set_log_session_state_change_hook",
    "set_log_message_processed_hook",
]
