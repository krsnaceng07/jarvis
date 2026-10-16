"""Session state and configuration resolution helpers for Teams Meetings."""

from __future__ import annotations

from .config import TeamsMeetingsConfig
from .transports.types import TeamsMeetingsSession


def is_browser_transport(transport: str | None) -> bool:
    return transport in ("chrome", "chrome-node", None)


def resolve_transport(transport: str | None, config: TeamsMeetingsConfig) -> str:
    return transport or config.default_transport or "chrome"


def resolve_mode(mode: str | None, config: TeamsMeetingsConfig) -> str:
    if mode == "realtime":
        return "agent"
    return mode or config.default_mode or "agent"


def note_session(session: TeamsMeetingsSession, note: str) -> None:
    if note and str(note).strip():
        session.notes.append(str(note).strip())


def with_session_agent_config(config: TeamsMeetingsConfig, agent_id: str) -> TeamsMeetingsConfig:
    return config
