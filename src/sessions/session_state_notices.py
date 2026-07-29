"""Stale-state session notices — text + context-key encoding.

Mirrors OpenClaw's ``extensions/sessions/session-state-notices.ts``:
- ``encode_notice_target`` / ``decode_session_state_notice_context_key``
  — hex-encode the target session key for queue dedupe
- ``session_state_notice_text`` — frozen watermark string
  used as the enqueued message
- ``is_notifiable_watcher_key`` / ``should_wake_watcher`` —
  cross-A2A metadata-leak guard
- ``enqueue_session_state_notice`` — enqueue + optional
  heartbeat wake (callable; uses injectable ``enqueue_system_event``
  + ``request_heartbeat`` for testability)

Python adaptations (documented in code):
- TS ``Buffer.from(x, "utf8").toString("hex")`` → Python
  ``x.encode("utf-8").hex()``
- TS infra deps (``enqueueSystemEvent``, ``requestHeartbeat``)
  are injected via module-level hooks so tests can stub them
  without monkey-patching.
"""
from __future__ import annotations

from typing import Callable, Optional

from .session_key_utils import is_subagent_session_key, parse_agent_session_key

# Prefix used for system-event context keys so consumers
# can recognize "this is a session-state notice" without
# parsing the whole context. Mirrors the TS
# ``SESSION_STATE_CONTEXT_PREFIX`` constant.
SESSION_STATE_CONTEXT_PREFIX = "session-state:"


def encode_notice_target(session_key: str) -> str:
    """Hex-encode a session key for use in a dedupe context key.

    Mirrors ``encodeNoticeTarget`` (private in the TS
    source). Uses UTF-8 + lowercase hex; the output is
    always a multiple-of-2 length.
    """
    return session_key.encode("utf-8").hex()


def decode_session_state_notice_context_key(
    context_key: str,
) -> Optional[str]:
    """Decode a session-state notice context key back to the target session key.

    Mirrors ``decodeSessionStateNoticeContextKey``.
    Returns ``None`` for:
    - missing prefix
    - empty encoded body
    - odd-length hex (not valid hex)
    - non-hex characters
    """
    if not context_key.startswith(SESSION_STATE_CONTEXT_PREFIX):
        return None
    encoded = context_key[len(SESSION_STATE_CONTEXT_PREFIX) :]
    if not encoded or len(encoded) % 2 != 0:
        return None
    try:
        return bytes.fromhex(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def session_state_notice_text(
    target_session_key: str, last_seen_sequence: int
) -> str:
    """Return the frozen-watermark notice text for a stale-state event.

    Mirrors the private ``sessionStateNoticeText``. Text is
    byte-stable so queue dedupe holds; the reconciliation
    call inside is self-contained (explicit target
    sessionKey).
    """
    return (
        f'Session "{target_session_key}" changed (other actor). '
        f'Reconcile before acting: session_status sessionKey '
        f'"{target_session_key}" changesSince {last_seen_sequence}.'
    )


def should_wake_watcher(watcher_session_key: str) -> bool:
    """Group activity is ambient context — only wake non-subagent watchers.

    Mirrors the private ``shouldWakeWatcher``.
    """
    return not is_subagent_session_key(watcher_session_key)


def is_notifiable_watcher_key(watcher_session_key: str) -> bool:
    """True for watchable (agent-scoped) session keys.

    Mirrors ``isNotifiableWatcherKey``: until watcher
    identity is agent-scoped end-to-end, bare keys (no
    agent wrapper) get durable events but no notices.
    """
    return parse_agent_session_key(watcher_session_key) is not None


# ── Pluggable infra hooks (test seam) ────────────────────────────


def _default_enqueue_system_event(message: str, options: dict) -> None:
    """Default enqueue_system_event no-op.

    Hosts wire the real ``enqueue_system_event`` via
    ``set_enqueue_system_event``. The Python port keeps
    the same call shape as the TS source (positional
    message + options dict with ``sessionKey`` /
    ``contextKey`` / ``replace``).
    """
    _ = message
    _ = options


def _default_request_heartbeat(options: dict) -> None:
    """Default request_heartbeat no-op.

    Hosts wire the real ``request_heartbeat`` via
    ``set_request_heartbeat``.
    """
    _ = options


_enqueue_system_event: Callable[[str, dict], None] = _default_enqueue_system_event
_request_heartbeat: Callable[[dict], None] = _default_request_heartbeat


def set_enqueue_system_event(fn: Callable[[str, dict], None]) -> None:
    """Inject a custom enqueue_system_event implementation (host-only)."""
    global _enqueue_system_event
    _enqueue_system_event = fn


def set_request_heartbeat(fn: Callable[[dict], None]) -> None:
    """Inject a custom request_heartbeat implementation (host-only)."""
    global _request_heartbeat
    _request_heartbeat = fn


def reset_session_state_notice_hooks_for_tests() -> None:
    """Reset the infra hooks to their no-op defaults. Test-only."""
    global _enqueue_system_event, _request_heartbeat
    _enqueue_system_event = _default_enqueue_system_event
    _request_heartbeat = _default_request_heartbeat


# ── Public enqueue ────────────────────────────────────────────────


def enqueue_session_state_notice(params: dict) -> None:
    """Enqueue a stale-state notice + optionally wake the watcher.

    Mirrors ``enqueueSessionStateNotice``. The
    ``queueOnly`` flag collapses group activity into the
    next main turn instead of waking the personal agent
    once per inbound group message.

    The Python port uses module-level hooks for the
    system-event queue + heartbeat wake (default to no-ops
    so the module is import-safe in tests).
    """
    watcher_key = params["watcherSessionKey"]
    target_key = params["targetSessionKey"]
    last_seen = params["lastSeenSequence"]
    queue_only = bool(params.get("queueOnly", False))

    _enqueue_system_event(
        session_state_notice_text(target_key, last_seen),
        {
            "sessionKey": watcher_key,
            "contextKey": (
                f"{SESSION_STATE_CONTEXT_PREFIX}"
                f"{encode_notice_target(target_key)}"
            ),
            **({"replace": True} if queue_only else {}),
        },
    )
    if queue_only:
        return
    if not should_wake_watcher(watcher_key):
        return
    _request_heartbeat(
        {
            "source": "session-state",
            "intent": "immediate",
            "reason": f"session-state:{target_key}",
            "sessionKey": watcher_key,
        }
    )


__all__ = [
    "SESSION_STATE_CONTEXT_PREFIX",
    "decode_session_state_notice_context_key",
    "encode_notice_target",
    "enqueue_session_state_notice",
    "is_notifiable_watcher_key",
    "reset_session_state_notice_hooks_for_tests",
    "session_state_notice_text",
    "set_enqueue_system_event",
    "set_request_heartbeat",
    "should_wake_watcher",
]
