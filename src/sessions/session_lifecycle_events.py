"""Session lifecycle + identity-mutation event bus.

Mirrors OpenClaw's ``extensions/sessions/session-lifecycle-events.ts``:
in-process listener registration + best-effort emit for
two event streams (lifecycle + identity mutation). The
Python port keeps the same process-wide ``Set[Listener]``
storage + ``on_*/emit_*`` function shape so plugins
port same-to-same.

Listeners run synchronously in registration order. Listener
errors are caught and swallowed (best-effort — one bad
listener must not break the others).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

# ── Lifecycle events ───────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SessionLifecycleEvent:
    """Session lifecycle event broadcast to observers.

    Mirrors the TS ``SessionLifecycleEvent`` type:
    ``reason`` is a free-form string identifying the
    transition (e.g. ``"created"``, ``"linked"``).
    ``parentSessionKey`` is set for child-session links.
    """

    session_key: str
    reason: str
    parent_session_key: Optional[str] = None
    label: Optional[str] = None
    display_name: Optional[str] = None


SessionLifecycleListener = Callable[[SessionLifecycleEvent], None]

# Process-wide listener registry. Uses a ``dict`` keyed on
# the listener (value ``None``) instead of a ``set`` so we
# get stable insertion-order iteration — the TS source
# uses ``Set`` which is insertion-ordered per the JS spec.
_SESSION_LIFECYCLE_LISTENERS: dict[SessionLifecycleListener, None] = {}


def on_session_lifecycle_event(
    listener: SessionLifecycleListener,
) -> Callable[[], None]:
    """Register a session lifecycle listener.

    Returns an unregister callable. Mirrors the TS
    ``onSessionLifecycleEvent``. Listeners are called in
    registration order on emit.
    """
    _SESSION_LIFECYCLE_LISTENERS[listener] = None

    def unregister() -> None:
        _SESSION_LIFECYCLE_LISTENERS.pop(listener, None)

    return unregister


def emit_session_lifecycle_event(event: SessionLifecycleEvent) -> None:
    """Best-effort fan-out to all session lifecycle listeners.

    Mirrors the TS ``emitSessionLifecycleEvent``: each
    listener is called in registration order, and any
    listener exception is caught so a single bad listener
    does not break the chain.
    """
    for listener in list(_SESSION_LIFECYCLE_LISTENERS.keys()):
        try:
            listener(event)
        except Exception:  # noqa: BLE001 — best-effort fan-out
            pass


# ── Identity mutation events ────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SessionIdentityMutationTarget:
    """Identity target — the previous or current ``SessionId`` + ``SessionKey[]`` pair."""

    session_id: Optional[str] = None
    session_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SessionIdentityMutation:
    """Identity mutation event (create / move / replace / reset / delete).

    Mirrors the TS ``SessionIdentityMutation`` discriminated
    union. The ``kind`` field is the literal:
    - ``"create"`` | ``"move"`` | ``"replace"`` | ``"reset"``: have
      both ``previous`` and ``current`` targets
    - ``"delete"``: only ``previous``
    """

    kind: str  # "create" | "move" | "replace" | "reset" | "delete"
    previous: SessionIdentityMutationTarget
    current: Optional[SessionIdentityMutationTarget] = None


SessionIdentityMutationListener = Callable[[SessionIdentityMutation], None]

# Insertion-ordered listener registry (see comment above
# on ``_SESSION_LIFECYCLE_LISTENERS``).
_SESSION_IDENTITY_MUTATION_LISTENERS: dict[SessionIdentityMutationListener, None] = {}


def on_session_identity_mutation(
    listener: SessionIdentityMutationListener,
) -> Callable[[], None]:
    """Register a session identity mutation listener.

    Returns an unregister callable. Mirrors the TS
    ``onSessionIdentityMutation``.
    """
    _SESSION_IDENTITY_MUTATION_LISTENERS[listener] = None

    def unregister() -> None:
        _SESSION_IDENTITY_MUTATION_LISTENERS.pop(listener, None)

    return unregister


def emit_session_identity_mutation(mutation: SessionIdentityMutation) -> None:
    """Best-effort fan-out to all identity-mutation listeners.

    Mirrors the TS ``emitSessionIdentityMutation``.
    Session persistence already succeeded; one observer
    must not block the rest.
    """
    for listener in list(_SESSION_IDENTITY_MUTATION_LISTENERS.keys()):
        try:
            listener(mutation)
        except Exception:  # noqa: BLE001 — best-effort fan-out
            pass


# ── Test helpers ─────────────────────────────────────────────────────


def _reset_session_lifecycle_listeners_for_tests() -> None:
    """Clear all listeners. Test-only helper."""
    _SESSION_LIFECYCLE_LISTENERS.clear()
    _SESSION_IDENTITY_MUTATION_LISTENERS.clear()


__all__ = [
    "SessionIdentityMutation",
    "SessionIdentityMutationListener",
    "SessionIdentityMutationTarget",
    "SessionLifecycleEvent",
    "SessionLifecycleListener",
    "_reset_session_lifecycle_listeners_for_tests",
    "emit_session_identity_mutation",
    "emit_session_lifecycle_event",
    "on_session_identity_mutation",
    "on_session_lifecycle_event",
]
