"""Session transcript event bus — listener registration + emit.

Mirrors OpenClaw's ``extensions/sessions/transcript-events.ts``:
the public + internal listener sets for session-transcript
updates, plus the normalizer that derives
``{sessionFile, target, sessionKey, agentId, sessionId, ...}``
from any partial update payload.

Public surface (mirrors the TS source):
- ``on_session_transcript_update(listener)`` → unregister
- ``on_internal_session_transcript_update(listener)`` → unregister
- ``emit_session_transcript_update(update)`` — fans out to
  both listener sets (after normalization)
- ``normalize_session_transcript_update(update, opts)`` —
  internal helper that trims + derives the canonical shape
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .session_key_utils import parse_agent_session_key

# ── Types ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SessionTranscriptUpdateTarget:
    """Storage-neutral identity for the session transcript that changed.

    Mirrors the TS ``SessionTranscriptUpdateTarget`` type.
    """

    agent_id: str
    session_id: str
    session_key: str


# The Python port uses a ``dict`` for the union-typed
# ``InternalSessionTranscriptUpdate`` to match the TS
# structural-typing pattern. Keys are optional; missing
# keys mean the field is absent.
InternalSessionTranscriptUpdate = dict[str, Any]

SessionTranscriptUpdate = dict[str, Any]

SessionTranscriptListener = Callable[[SessionTranscriptUpdate], None]
InternalSessionTranscriptListener = Callable[[InternalSessionTranscriptUpdate], None]

# Insertion-ordered listener registries (TS ``Set``).
_SESSION_TRANSCRIPT_LISTENERS: dict[SessionTranscriptListener, None] = {}
_INTERNAL_SESSION_TRANSCRIPT_LISTENERS: dict[InternalSessionTranscriptListener, None] = {}


# ── Public listener registration ──────────────────────────────────


def on_session_transcript_update(
    listener: SessionTranscriptListener,
) -> Callable[[], None]:
    """Register a public session-transcript listener.

    Returns an unregister callable. Mirrors
    ``onSessionTranscriptUpdate``. Listeners are called in
    registration order on emit.
    """
    _SESSION_TRANSCRIPT_LISTENERS[listener] = None

    def unregister() -> None:
        _SESSION_TRANSCRIPT_LISTENERS.pop(listener, None)

    return unregister


def on_internal_session_transcript_update(
    listener: InternalSessionTranscriptListener,
) -> Callable[[], None]:
    """Register an internal (identity-only or file-backed) listener."""
    _INTERNAL_SESSION_TRANSCRIPT_LISTENERS[listener] = None

    def unregister() -> None:
        _INTERNAL_SESSION_TRANSCRIPT_LISTENERS.pop(listener, None)

    return unregister


# ── Emit + normalize ─────────────────────────────────────────────


def _normalize_optional_string(value: Any) -> Optional[str]:
    """Return the trimmed value, or ``None`` for empty/non-string.

    Mirrors OpenClaw's ``normalizeOptionalString``.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _as_positive_safe_integer(value: Any) -> Optional[int]:
    """Return ``int(value)`` for positive integers, else ``None``.

    Mirrors ``asPositiveSafeInteger`` from
    ``@openclaw/normalization-core/number-coercion``.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str):
        try:
            n = int(value.strip())
        except (TypeError, ValueError):
            return None
        if n > 0:
            return n
    return None


def _normalize_update_target(
    update: InternalSessionTranscriptUpdate,
) -> Optional[SessionTranscriptUpdateTarget]:
    """Derive the canonical ``target`` shape from any partial update.

    Mirrors ``normalizeUpdateTarget`` (private). Returns
    ``None`` when any required field is missing.
    """
    target = update.get("target")
    session_key = _normalize_optional_string(
        target.get("sessionKey") if isinstance(target, dict) else None
    ) or _normalize_optional_string(update.get("sessionKey"))
    agent_id_raw = target.get("agentId") if isinstance(target, dict) else None
    parsed_key = parse_agent_session_key(session_key) if session_key else None
    parsed_agent = parsed_key.agent_id if parsed_key is not None else None
    agent_id = (
        _normalize_optional_string(agent_id_raw)
        or _normalize_optional_string(update.get("agentId"))
        or parsed_agent
    )
    session_id_target = target.get("sessionId") if isinstance(target, dict) else None
    session_id = _normalize_optional_string(session_id_target) or _normalize_optional_string(
        update.get("sessionId")
    )
    if not agent_id or not session_id or not session_key:
        return None
    return SessionTranscriptUpdateTarget(
        agent_id=agent_id,
        session_id=session_id,
        session_key=session_key,
    )


def normalize_session_transcript_update(
    update: InternalSessionTranscriptUpdate,
    options: dict[str, Any],
) -> Optional[InternalSessionTranscriptUpdate]:
    """Normalize a transcript update to the canonical trimmed shape.

    Mirrors ``normalizeSessionTranscriptUpdate`` (private).
    Returns ``None`` when the update is missing required
    fields (``sessionFile`` or ``target``, depending on
    ``options.allowIdentityOnly``).
    """
    allow_identity_only = bool(options.get("allowIdentityOnly", False))
    trimmed_file = _normalize_optional_string(update.get("sessionFile"))
    target = _normalize_update_target(update)
    if not trimmed_file and not (allow_identity_only and target):
        return None
    message_seq = _as_positive_safe_integer(update.get("messageSeq"))
    session_key = _normalize_optional_string(update.get("sessionKey")) or (
        target.session_key if target else None
    )
    agent_id = _normalize_optional_string(update.get("agentId")) or (
        target.agent_id if target else None
    )
    session_id = _normalize_optional_string(update.get("sessionId")) or (
        target.session_id if target else None
    )
    message_id = _normalize_optional_string(update.get("messageId"))
    normalized: InternalSessionTranscriptUpdate = {}
    if trimmed_file:
        normalized["sessionFile"] = trimmed_file
    if target:
        normalized["target"] = target
    if session_key:
        normalized["sessionKey"] = session_key
    if agent_id:
        normalized["agentId"] = agent_id
    if session_id:
        normalized["sessionId"] = session_id
    if "message" in update:
        normalized["message"] = update["message"]
    if message_id:
        normalized["messageId"] = message_id
    if message_seq is not None:
        normalized["messageSeq"] = message_seq
    return normalized


def _project_public_session_transcript_update(
    update: InternalSessionTranscriptUpdate,
) -> Optional[SessionTranscriptUpdate]:
    """Project the public (file-required) shape from a normalized update.

    Mirrors ``projectPublicSessionTranscriptUpdate`` (private).
    """
    target = update.get("target")
    if not target:
        return None
    out: SessionTranscriptUpdate = {"target": target}
    if update.get("sessionKey"):
        out["sessionKey"] = update["sessionKey"]
    if update.get("agentId"):
        out["agentId"] = update["agentId"]
    if update.get("sessionId"):
        out["sessionId"] = update["sessionId"]
    if "message" in update:
        out["message"] = update["message"]
    if update.get("messageId"):
        out["messageId"] = update["messageId"]
    if "messageSeq" in update:
        out["messageSeq"] = update["messageSeq"]
    return out


def _emit_public_session_transcript_update(
    update: SessionTranscriptUpdate,
) -> None:
    for listener in list(_SESSION_TRANSCRIPT_LISTENERS.keys()):
        try:
            listener(update)
        except Exception:  # noqa: BLE001 — best-effort fan-out
            pass


def _emit_internal_session_transcript_update(
    update: InternalSessionTranscriptUpdate,
) -> None:
    for listener in list(_INTERNAL_SESSION_TRANSCRIPT_LISTENERS.keys()):
        try:
            listener(update)
        except Exception:  # noqa: BLE001 — best-effort fan-out
            pass


def emit_session_transcript_update(update: InternalSessionTranscriptUpdate) -> None:
    """Fan out a transcript update to public + internal listeners.

    Mirrors ``emitSessionTranscriptUpdate``. First
    normalizes (with ``allowIdentityOnly=True`` so identity
    updates reach the internal listener set), then projects
    the public shape for the public listener set, then
    fires both. Listener exceptions are swallowed
    (best-effort fan-out).
    """
    normalized = normalize_session_transcript_update(update, {"allowIdentityOnly": True})
    if normalized is None:
        return
    public = _project_public_session_transcript_update(normalized)
    if public is not None:
        _emit_public_session_transcript_update(public)
    _emit_internal_session_transcript_update(normalized)


# ── Test helpers ───────────────────────────────────────────────────


def _reset_transcript_event_listeners_for_tests() -> None:
    """Clear all listeners. Test-only helper."""
    _SESSION_TRANSCRIPT_LISTENERS.clear()
    _INTERNAL_SESSION_TRANSCRIPT_LISTENERS.clear()


__all__ = [
    "InternalSessionTranscriptUpdate",
    "SessionTranscriptListener",
    "SessionTranscriptUpdate",
    "SessionTranscriptUpdateTarget",
    "_reset_transcript_event_listeners_for_tests",
    "emit_session_transcript_update",
    "normalize_session_transcript_update",
    "on_internal_session_transcript_update",
    "on_session_transcript_update",
]
