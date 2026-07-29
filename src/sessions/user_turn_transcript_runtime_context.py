"""Transient user-turn transcript context carried through runtime queues.

Mirrors OpenClaw's
``src/sessions/user-turn-transcript-runtime-context.ts``.

The TS source uses two ``Symbol.for(...)`` keys to attach
transient metadata to a runtime message without exposing it
to the model:

- ``openclaw.runtimeUserTurnTranscriptContext`` — the
  message + recorder pair consumed right before the message
  is serialized.
- ``openclaw.runtimeUserTurnTranscriptRecorder`` — the
  recorder that stays attached to the final message until
  persistence succeeds.

The Python port uses the same string keys (the
``Symbol.for(...)`` lookup in TS is just a process-wide
symbol registry keyed by string).

Public surface (mirrors the TS source):
- ``attach_runtime_user_turn_transcript_context(message, context)``
- ``take_runtime_user_turn_transcript_context(message)``
- ``attach_runtime_user_turn_transcript_recorder(message, recorder)``
- ``take_runtime_user_turn_transcript_recorder(message)``

Python adaptations (documented in code):
- TS ``Object.defineProperty(message, Symbol, { configurable, value })``
  → Python attribute set on a thin wrapper object. The TS
  pattern is "attach without enumerability"; the Python
  equivalent stores the value as a private attribute on a
  small carrier class.
- TS ``Symbol.for("...")`` keys → Python string keys
- TS ``Extract<AgentMessage, { role: "user" }>`` →
  ``UserTurnMessage`` TypedDict (a thin structural alias)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict

# Public key constants (mirrors the TS Symbol.for keys).
KEY_RUNTIME_USER_TURN_TRANSCRIPT_CONTEXT = (
    "openclaw.runtimeUserTurnTranscriptContext"
)
KEY_RUNTIME_USER_TURN_TRANSCRIPT_RECORDER = (
    "openclaw.runtimeUserTurnTranscriptRecorder"
)


# Structural aliases for the message and recorder types.
class UserTurnMessage(TypedDict, total=False):
    role: str
    content: Any
    # ...mirrors the OpenClaw PersistedUserTurnMessage shape;
    # the helper does not depend on the full contract.
    text: str


class UserTurnTranscriptRecorder(TypedDict, total=False):
    message: Optional[UserTurnMessage]
    resolveMessage: Any
    getPersistedMessage: Any
    markSentToProvider: Any
    markRuntimePersistencePending: Any
    markRuntimePersisted: Any
    markBlocked: Any
    hasPersisted: Any
    isBlocked: Any
    hasRuntimePersistencePending: Any
    waitForRuntimePersistence: Any
    persistApproved: Any
    persistBlocked: Any
    persistFallback: Any


@dataclass
class RuntimeUserTurnTranscriptContext:
    """Pair of (message, recorder) carried with a runtime message.

    Mirrors the TS ``RuntimeUserTurnTranscriptContext`` type.
    """

    message: UserTurnMessage
    recorder: UserTurnTranscriptRecorder


@dataclass
class _RuntimeCarrier:
    """Thin wrapper that holds the two runtime context slots.

    Mirrors the TS ``Object.defineProperty(message, Symbol, ...)``
    pattern: the carrier stores the transient metadata in
    private attributes so it does not surface in
    ``vars(message)`` or ``message.__dict__`` (callers
    interact through the public take/attach helpers).
    """

    payload: Any
    _transcript_context: Optional[RuntimeUserTurnTranscriptContext] = field(
        default=None, init=False
    )
    _transcript_recorder: Optional[UserTurnTranscriptRecorder] = field(
        default=None, init=False
    )


def _coerce(message: Any) -> _RuntimeCarrier:
    """Return the runtime carrier that wraps ``message``.

    If ``message`` is already a ``_RuntimeCarrier``, return
    it as-is. Otherwise wrap it in a fresh carrier.
    """
    if isinstance(message, _RuntimeCarrier):
        return message
    return _RuntimeCarrier(payload=message)


def _unwrap(carrier: _RuntimeCarrier) -> Any:
    """Return the original message that was wrapped."""
    return carrier.payload


# ── Public surface ────────────────────────────────────────


def attach_runtime_user_turn_transcript_context(
    runtime_message: Any,
    context: RuntimeUserTurnTranscriptContext,
) -> Any:
    """Attach a transcript-only context to ``runtime_message``.

    Mirrors ``attachRuntimeUserTurnTranscriptContext``.
    Carries transcript-only fields with a queued runtime
    message without exposing them to the model.
    """
    carrier = _coerce(runtime_message)
    carrier._transcript_context = context
    return carrier


def take_runtime_user_turn_transcript_context(
    runtime_message: Any,
) -> Optional[RuntimeUserTurnTranscriptContext]:
    """Consume the transient queued-turn context.

    Mirrors ``takeRuntimeUserTurnTranscriptContext``. The
    context is removed from the carrier and returned (or
    ``None`` when no context was attached).
    """
    carrier = _coerce(runtime_message)
    context = carrier._transcript_context
    if context is not None:
        carrier._transcript_context = None
    return context


def attach_runtime_user_turn_transcript_recorder(
    runtime_message: Any,
    recorder: UserTurnTranscriptRecorder,
) -> Any:
    """Keep the queued recorder attached to the exact final message.

    Mirrors ``attachRuntimeUserTurnTranscriptRecorder``. The
    recorder stays attached until persistence succeeds.
    """
    carrier = _coerce(runtime_message)
    carrier._transcript_recorder = recorder
    return carrier


def take_runtime_user_turn_transcript_recorder(
    runtime_message: Any,
) -> Optional[UserTurnTranscriptRecorder]:
    """Consume the transient recorder from a runtime message.

    Mirrors ``takeRuntimeUserTurnTranscriptRecorder``. The
    recorder is removed from the carrier and returned (or
    ``None`` when no recorder was attached).
    """
    carrier = _coerce(runtime_message)
    recorder = carrier._transcript_recorder
    if recorder is not None:
        carrier._transcript_recorder = None
    return recorder


__all__ = [
    "KEY_RUNTIME_USER_TURN_TRANSCRIPT_CONTEXT",
    "KEY_RUNTIME_USER_TURN_TRANSCRIPT_RECORDER",
    "RuntimeUserTurnTranscriptContext",
    "UserTurnMessage",
    "UserTurnTranscriptRecorder",
    "attach_runtime_user_turn_transcript_context",
    "attach_runtime_user_turn_transcript_recorder",
    "take_runtime_user_turn_transcript_context",
    "take_runtime_user_turn_transcript_recorder",
]
