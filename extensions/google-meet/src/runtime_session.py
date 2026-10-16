"""Session resolution and utility helpers for Google Meet."""

from __future__ import annotations

from dataclasses import replace

from .config import GoogleMeetConfig
from .transports.types import GoogleMeetSession


def resolve_transport(
    input_transport: str | None,
    config: GoogleMeetConfig,
) -> str:
    return input_transport or config.default_transport


def resolve_mode(
    input_mode: str | None,
    config: GoogleMeetConfig,
) -> str:
    if input_mode == "realtime":
        return "agent"
    return input_mode or config.default_mode


def with_session_agent_config(
    config: GoogleMeetConfig,
    agent_id: str,
) -> GoogleMeetConfig:
    if config.realtime.agent_id == agent_id:
        return config
    new_realtime = replace(config.realtime, agent_id=agent_id)
    return replace(config, realtime=new_realtime)


def is_browser_transport(transport: str) -> bool:
    return transport in ("chrome", "chrome-node")


def note_session(session: GoogleMeetSession, note: str) -> None:
    session.notes = [n for n in session.notes if n != note] + [note]
