"""Conversation turn correlation between Gateway RPC and inbound dispatch.

Mirrors OpenClaw's ``extensions/sessions/conversation-turns.ts``:
process-wide registry of pending outbound turns so the
Gateway RPC execution and inbound dispatch (which can
live in different bundled chunks) can correlate replies
to the originating turns.

Public surface (mirrors the TS source):
- ``register_pending_conversation_turn(params)`` —
  register a wait for one turn; returns a handle
- ``cancel_pending_conversation_turn(params)`` — cancel
- ``claim_pending_conversation_turn_reply(params)`` —
  claim an inbound reply against a pending turn

Python adaptations (documented in code):
- TS ``crypto.randomUUID()`` → Python ``uuid.uuid4()``
- TS ``AbortSignal`` → Python boolean + ``on_cancel``
  callable (Python's stdlib doesn't have a single
  equivalent in 3.13+ without ``asyncio``)
- TS ``setTimeout(..., unref)`` → Python
  ``threading.Timer`` (no equivalent of ``unref`` in CPython;
  the timer is daemon-fire-and-forget)
- TS ``Map`` (insertion-ordered) → Python ``dict``
- TS ``resolveGlobalSingleton`` → ``resolve_global_singleton``
  (same Symbol.for() key for cross-module sharing)
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from shared.global_singleton import resolve_global_singleton

# Process-wide pending-turn registry. The TS source uses
# ``Symbol.for("openclaw.pendingConversationTurns")`` to share
# the same Map across bundled chunks; the Python port uses
# the same string key.
_PENDING_TURNS_KEY = "openclaw.pendingConversationTurns"
_pending_turns: dict[str, "PendingConversationTurn"] = resolve_global_singleton(
    _PENDING_TURNS_KEY, lambda: {}
)


# ── Types ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ConversationTurnReply:
    """Final reply delivered to the waiting turn.

    Mirrors the TS ``ConversationTurnReply`` type.
    """

    conversation_ref: str
    message_id: str
    text: str
    timestamp: int
    reply_to_id: Optional[str] = None
    thread_id: Optional[str] = None
    transcript_artifact_id: Optional[str] = None
    transcript_message_id: Optional[str] = None


@dataclass
class PendingConversationTurn:
    """One in-flight outbound turn waiting for a correlated reply."""

    key: str
    agent_id: str
    id: str
    conversation_ref: str
    session_id: str
    created_at: int
    thread_id: Optional[str] = None
    outbound_message_id: Optional[str] = None
    claimed: bool = False
    correlation_ready: threading.Event = field(default_factory=threading.Event)
    mark_correlation_ready: Callable[[], None] = field(default=lambda: None)
    stop_timeout: Callable[[], None] = field(default=lambda: None)
    settle: Callable[[Optional[ConversationTurnReply]], None] = field(default=lambda r: None)


@dataclass(frozen=True, slots=True)
class PendingConversationTurnHandle:
    """Handle returned by ``register_pending_conversation_turn``."""

    id: str
    set_outbound_message_id: Callable[[Optional[str]], None]
    mark_ready: Callable[[], None]
    wait: Callable[[], Any]  # async-awaitable → returns ConversationTurnReply | None
    cancel: Callable[[], None]


@dataclass(frozen=True, slots=True)
class ConversationTurnReplyClaim:
    """Claim handle returned by ``claim_pending_conversation_turn_reply``."""

    turn_id: str
    session_id: str
    complete: Callable[[Optional[dict]], None]
    release: Callable[[], None]


# ── Helpers ──────────────────────────────────────────────────────


def _normalize(value: object) -> Optional[str]:
    """Trim a string value, returning ``None`` for empty/non-string.

    Mirrors the TS ``normalize`` (private) helper.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _pending_turn_key(agent_id: str, turn_id: str) -> str:
    """Build the Map key for a pending turn.

    Mirrors ``pendingTurnKey`` (private).
    """
    import json

    return json.dumps([agent_id, turn_id], separators=(",", ":"))


# ── Public surface ────────────────────────────────────────────────


def register_pending_conversation_turn(params: dict) -> PendingConversationTurnHandle:
    """Register a wait for one turn.

    Mirrors ``registerPendingConversationTurn``. Returns a
    handle that the caller can use to set the outbound
    message id, mark the turn ready, await the reply, or
    cancel the wait.
    """
    agent_id = _normalize(params.get("agentId"))
    if not agent_id:
        raise ValueError("conversation turn requires an agent id")
    turn_id = _normalize(params.get("id")) or str(uuid.uuid4())
    key = _pending_turn_key(agent_id, turn_id)
    if key in _pending_turns:
        raise RuntimeError(f"conversation turn already pending for {agent_id}: {turn_id}")
    created_at = int(params.get("createdAt") or 0) or _now_ms()
    timeout_ms = max(0, int(params.get("timeoutMs", 0)))
    correlation_event = threading.Event()
    reply_holder: dict = {"reply": None}
    settled = {"done": False}
    cancel_signal = params.get("signal")

    def mark_correlation_ready() -> None:
        correlation_event.set()

    def stop_timeout() -> None:
        # ``timer`` is captured by closure below; this stops it.
        timer_ref["timer"].cancel() if timer_ref.get("timer") else None

    timer_ref: dict = {"timer": None}

    def settle(reply: Optional[ConversationTurnReply]) -> None:
        if settled["done"]:
            return
        settled["done"] = True
        mark_correlation_ready()
        # Only delete if we're still the current pending turn
        if _pending_turns.get(key) is pending:
            del _pending_turns[key]
        stop_timeout()
        # If a cancel signal was provided, detach our listener
        if cancel_signal is not None and hasattr(cancel_signal, "_pending_turns_remove_listener"):
            try:
                cancel_signal._pending_turns_remove_listener(cancel)
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass
        reply_holder["reply"] = reply

    def cancel() -> None:
        settle(None)

    pending = PendingConversationTurn(
        key=key,
        agent_id=agent_id,
        id=turn_id,
        conversation_ref=params.get("conversationRef", ""),
        session_id=params.get("sessionId", ""),
        created_at=created_at,
        thread_id=_normalize(params.get("threadId")),
        correlation_ready=correlation_event,
        mark_correlation_ready=mark_correlation_ready,
        stop_timeout=stop_timeout,
        settle=settle,
    )
    _pending_turns[key] = pending

    # Schedule the timeout. Use ``threading.Timer`` (not
    # ``asyncio``) so the registry works from any thread.
    if timeout_ms > 0:
        # Keep a tiny scheduling grace so callers measuring from ``wait()`` do
        # not observe a timeout early when registration/setup consumed part of
        # the requested interval on coarse Windows timers.
        timer = threading.Timer((timeout_ms + 1) / 1000.0, cancel)
        timer.daemon = True
        timer_ref["timer"] = timer
        timer.start()

    async def _wait() -> Optional[ConversationTurnReply]:
        # Block on the correlation event; the reply is
        # captured in ``reply_holder`` by the timeout /
        # complete path. Returning the reply at this point
        # is safe — by the time the event is set, ``settle``
        # has already populated ``reply_holder``.
        import asyncio

        # Run the wait in a thread so we don't block the event loop
        await asyncio.get_event_loop().run_in_executor(None, correlation_event.wait)
        return reply_holder["reply"]

    return PendingConversationTurnHandle(
        id=turn_id,
        set_outbound_message_id=lambda message_id: _set_outbound_message_id(
            pending, key, message_id
        ),
        mark_ready=lambda: _mark_ready(pending, key),
        wait=_wait,
        cancel=cancel,
    )


def _now_ms() -> int:
    """Current epoch milliseconds (Python doesn't have a built-in)."""
    import time

    return int(time.time() * 1000)


def _set_outbound_message_id(
    pending: PendingConversationTurn, key: str, message_id: Optional[str]
) -> None:
    """Set the outbound message id; settle if message_id is None.

    Mirrors the ``setOutboundMessageId`` body in the TS source.
    """
    if _pending_turns.get(key) is not pending:
        return
    pending.outbound_message_id = _normalize(message_id)
    if not pending.outbound_message_id:
        pending.settle(None)


def _mark_ready(pending: PendingConversationTurn, key: str) -> None:
    """Mark the turn ready; settles with None if no outbound id.

    Mirrors the ``markReady`` body in the TS source.
    """
    if _pending_turns.get(key) is not pending:
        return
    if pending.outbound_message_id:
        pending.mark_correlation_ready()
    else:
        pending.settle(None)


def cancel_pending_conversation_turn(params: dict) -> bool:
    """Cancel one Gateway-owned turn so a late reply follows ordinary inbound dispatch.

    Mirrors ``cancelPendingConversationTurn``. Returns
    ``True`` when a pending turn was found and settled.
    """
    agent_id = _normalize(params.get("agentId"))
    turn_id = _normalize(params.get("id"))
    pending = (
        _pending_turns.get(_pending_turn_key(agent_id, turn_id)) if agent_id and turn_id else None
    )
    if pending is None:
        return False
    pending.settle(None)
    return True


async def claim_pending_conversation_turn_reply(
    params: dict,
) -> Optional[ConversationTurnReplyClaim]:
    """Claim an inbound reply for a pending turn.

    Mirrors ``claimPendingConversationTurnReply``. Returns
    ``None`` when no matching pending turn exists. The
    returned claim exposes ``complete`` / ``release``
    callbacks for the caller to commit or rollback the
    correlation.
    """
    reply_to_id = _normalize(params.get("replyToId"))
    if not reply_to_id:
        return None
    thread_id = _normalize(params.get("threadId"))
    parent_conversation_ref = _normalize(params.get("parentConversationRef"))
    agent_id = _normalize(params.get("agentId"))
    if not agent_id:
        return None

    conversation_ref = params.get("conversationRef", "")
    session_id = params.get("sessionId", "")

    # Find matching pending turn: same agent, same conversation
    # (or promoted-thread case), same session, optional thread
    # match. Sort by createdAt ascending (oldest first), then
    # pick the one whose outbound_message_id matches reply_to_id.
    candidates = [
        candidate
        for candidate in _pending_turns.values()
        if not candidate.claimed
        and candidate.agent_id == agent_id
        and (
            candidate.conversation_ref == conversation_ref
            or (
                not candidate.thread_id
                and thread_id == reply_to_id
                and parent_conversation_ref == candidate.conversation_ref
            )
        )
        and candidate.session_id == session_id
        and (not candidate.thread_id or not thread_id or candidate.thread_id == thread_id)
    ]
    candidates.sort(key=lambda c: c.created_at)
    pending = next(
        (c for c in candidates if c.outbound_message_id == reply_to_id),
        None,
    )
    if pending is None:
        return None
    pending.claimed = True
    # Only an exact transport match can wait for outbound
    # transcript durability.
    if not pending.correlation_ready.wait(timeout=30.0):
        # Timeout: release the claim.
        if _pending_turns.get(pending.key) is pending:
            pending.claimed = False
        return None
    if _pending_turns.get(pending.key) is not pending:
        return None
    timestamp = int(params.get("timestamp") or 0) or _now_ms()
    reply = ConversationTurnReply(
        conversation_ref=conversation_ref,
        message_id=params.get("messageId", ""),
        text=params.get("text", ""),
        timestamp=timestamp,
        reply_to_id=reply_to_id,
        thread_id=thread_id,
    )

    def complete(completion: Optional[dict] = None) -> None:
        completion = completion or {}
        merged = ConversationTurnReply(
            conversation_ref=reply.conversation_ref,
            message_id=reply.message_id,
            text=reply.text,
            timestamp=reply.timestamp,
            reply_to_id=reply.reply_to_id,
            thread_id=reply.thread_id,
            transcript_artifact_id=completion.get("transcriptArtifactId"),
            transcript_message_id=completion.get("transcriptMessageId"),
        )
        pending.settle(merged)

    def release() -> None:
        # Persistence can fail after a transport reply was
        # claimed. Keep the waiter alive so a transport
        # retry can claim it before the deadline.
        if _pending_turns.get(pending.key) is pending:
            pending.claimed = False

    return ConversationTurnReplyClaim(
        turn_id=pending.id,
        session_id=pending.session_id,
        complete=complete,
        release=release,
    )


# ── Test helpers ───────────────────────────────────────────────────


def _reset_pending_turns_for_tests() -> None:
    """Clear all pending turns. Test-only helper."""
    _pending_turns.clear()


__all__ = [
    "ConversationTurnReply",
    "ConversationTurnReplyClaim",
    "PendingConversationTurnHandle",
    "_reset_pending_turns_for_tests",
    "cancel_pending_conversation_turn",
    "claim_pending_conversation_turn_reply",
    "register_pending_conversation_turn",
]
