"""Session state event kinds + their notification policy.

Mirrors OpenClaw's ``extensions/sessions/session-state-event-kinds.ts``:
the closed set of ``SessionStateEventKind`` strings + a
constant map indicating whether each kind is notify-worthy
(via UI/system notifications). The Python port uses
``frozenset`` for the kind union and a ``dict`` for the
notify map; the API is identical.
"""

from __future__ import annotations

from typing import Literal

# Closed union of session state event kinds. Matches the
# OpenClaw ``SessionStateEventKind`` discriminated union.
SessionStateActorType = Literal["human", "agent", "system"]

SessionStateEventKind = Literal[
    "human_direct_message",
    "adopted",
    "run_completed",
    "run_failed",
    "child_spawned",
    "goal_changed",
    "upstream_missing",
    "compacted",
]

# Notify-policy table. ``True`` means the host should surface
# this event kind as a UI/system notification; ``False``
# means it's only useful for internal state machines.
# Mirrors the TS ``NOTIFY_BY_SESSION_STATE_EVENT_KIND``
# constant.
NOTIFY_BY_SESSION_STATE_EVENT_KIND: dict[SessionStateEventKind, bool] = {
    "human_direct_message": True,
    "upstream_missing": True,
    "adopted": False,
    "goal_changed": True,
    "run_completed": False,
    "run_failed": False,
    "child_spawned": False,
    "compacted": False,
}


__all__ = [
    "NOTIFY_BY_SESSION_STATE_EVENT_KIND",
    "SessionStateActorType",
    "SessionStateEventKind",
]
