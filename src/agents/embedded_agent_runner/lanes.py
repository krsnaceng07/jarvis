"""jarvis.agents.embedded_agent_runner.lanes — command queue lane names.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/lanes.ts``.

Public surface (mirrors the OpenClaw
source):

- :class:`CommandLane` — the
  built-in lane names.
- :func:`resolve_session_lane` —
  resolve a session-specific lane.
- :func:`resolve_global_lane` —
  resolve a global lane.
- :func:`resolve_embedded_session_lane` —
  resolve an embedded-agent session
  lane (alias for
  :func:`resolve_session_lane`).

Phase 7.0 — focused minimal port.
"""
from __future__ import annotations

from typing import Optional


class CommandLane:
    """The built-in command-queue
    lane names. Mirrors
    :class:`CommandLane`
    (``lanes.ts:5`` — the OpenClaw
    source uses ``CommandLane``
    as a TypeScript namespace with
    string constants)."""

    Main: str = "main"
    Cron: str = "cron"
    CronNested: str = "cron-nested"


def resolve_session_lane(key: str) -> str:
    """Resolve a session-specific lane.
    Mirrors :func:`resolveSessionLane`
    (``lanes.ts:6-9``).

    The OpenClaw source prefixes
    the key with ``"session:"`` (and
    defaults to the ``Main`` lane for
    empty keys).
    """
    cleaned = (key or "").strip()
    if not cleaned:
        return CommandLane.Main
    if cleaned.startswith("session:"):
        return cleaned
    return f"session:{cleaned}"


def resolve_global_lane(lane: Optional[str] = None) -> str:
    """Resolve a global lane. Mirrors
    :func:`resolveGlobalLane`
    (``lanes.ts:11-19``)."""
    if lane is None:
        return CommandLane.Main
    cleaned = lane.strip()
    if not cleaned:
        return CommandLane.Main
    if cleaned == CommandLane.Cron:
        return CommandLane.CronNested
    return cleaned


def resolve_embedded_session_lane(key: str) -> str:
    """Resolve an embedded-agent
    session lane. Mirrors
    :func:`resolveEmbeddedSessionLane`
    (``lanes.ts:21-23``) — alias
    for :func:`resolve_session_lane`."""
    return resolve_session_lane(key)


__all__ = [
    "CommandLane",
    "resolve_embedded_session_lane",
    "resolve_global_lane",
    "resolve_session_lane",
]
