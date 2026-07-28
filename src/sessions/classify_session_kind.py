"""jarvis.sessions.classify_session_kind — session-kind classification.

OpenClaw parity: mirrors ``src/sessions/classify-session-kind.ts``.

A session is one of: ``direct`` (1:1 DM / private channel
member), ``channel`` (group or channel-style room),
``thread`` (sub-thread of a channel), ``cron`` (scheduled
job), or ``unknown`` (anything we can't classify). The
classifier is a lightweight, side-effect-free helper that
the host uses to pick the right transcript / agent surface.
"""
from __future__ import annotations

from typing import Any

_VALID_KINDS = ("direct", "channel", "thread", "cron", "unknown")


def classify_session_kind(value: Any) -> str:
    """Return the session kind for ``value``; falls back to ``"unknown"``.

    Mirrors OpenClaw's ``classifySessionKind``:
    - ``None`` / empty / non-string → ``"unknown"``
    - strings ending in ``"unknown"`` (case-insensitive) →
      ``"unknown"`` (the canonical "unscoped" sentinel)
    - strings containing the marker ``":cron:"`` →
      ``"cron"``
    - strings whose first non-prefix segment is
      ``"direct"`` or ``"dm"`` → ``"direct"``
    - strings whose first non-prefix segment is
      ``"channel"``, ``"group"``, ``"room"``, or contains
      a guild-like prefix → ``"channel"``
    - strings whose first non-prefix segment is
      ``"thread"`` → ``"thread"``
    - everything else → ``"unknown"``
    """
    if not isinstance(value, str):
        return "unknown"
    raw = value.strip()
    if not raw:
        return "unknown"
    if raw.lower() == "unknown":
        return "unknown"
    if ":cron:" in raw:
        return "cron"
    segments = [s.lower() for s in raw.split(":") if s]
    # A "thread" is the deepest sub-session; check it first.
    if "thread" in segments:
        return "thread"
    # The peer-kind marker is the segment right after the channel name.
    # Walk segments from the right: the second-to-last segment
    # is the kind (direct/dm/channel/group/room).
    if len(segments) >= 2:
        peer_kind = segments[-2]
        if peer_kind in ("direct", "dm"):
            return "direct"
        if peer_kind in ("channel", "group", "room"):
            return "channel"
    return "unknown"


def is_valid_session_kind(value: Any) -> bool:
    """Return True if ``value`` is a recognized session-kind string."""
    return isinstance(value, str) and value in _VALID_KINDS


__all__ = ["classify_session_kind", "is_valid_session_kind"]
