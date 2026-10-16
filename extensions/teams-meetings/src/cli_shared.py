"""Shared formatting, parsing, and execution routines for Teams Meetings CLI commands."""

from __future__ import annotations

import json
import sys
from typing import Any

from .transports.types import TeamsMeetingsSession


def write_stdout_json(value: Any) -> None:
    if hasattr(value, "__dict__"):
        val_dict = getattr(value, "__dict__")
        sys.stdout.write(f"{json.dumps(val_dict, indent=2, default=str)}\n")
    else:
        sys.stdout.write(f"{json.dumps(value, indent=2, default=str)}\n")
    sys.stdout.flush()


def write_stdout_line(fmt: str, *args: Any) -> None:
    if args:
        try:
            sys.stdout.write(f"{fmt % args}\n")
        except Exception:
            sys.stdout.write(f"{fmt.format(*args)}\n")
    else:
        sys.stdout.write(f"{fmt}\n")
    sys.stdout.flush()


def write_output(ctx: Any, payload: Any, is_error: bool = False) -> None:
    json_mode = getattr(ctx, "json_mode", False)
    if json_mode or is_error or isinstance(payload, (dict, list)):
        write_stdout_json(payload)
    else:
        write_stdout_line("%s", payload)


def format_boolean(value: bool | None) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return "unknown"


def format_optional(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value
    if value is not None and not isinstance(value, str):
        return str(value)
    return "n/a"


def write_doctor_status(status: Any) -> None:
    if not status:
        write_stdout_line("Teams meeting session: not found")
        return

    sessions = (
        status
        if isinstance(status, list)
        else ([status] if isinstance(status, TeamsMeetingsSession) else [])
    )
    if not sessions:
        write_stdout_line("Teams meeting sessions: none")
        return

    write_stdout_line("Teams meeting sessions: %d", len(sessions))
    for session in sessions:
        health = session.chrome.health if session.chrome else None
        write_stdout_line("")
        write_stdout_line("session: %s", session.id)
        write_stdout_line("url: %s", session.url)
        write_stdout_line("state: %s", session.state)
        write_stdout_line("transport: %s", session.transport)
        write_stdout_line("mode: %s", session.mode)
        if session.chrome:
            write_stdout_line("node: %s", session.chrome.node_id or "local/none")
            write_stdout_line("in call: %s", format_boolean(health.in_call if health else None))
            write_stdout_line(
                "lobby waiting: %s", format_boolean(health.lobby_waiting if health else None)
            )
            write_stdout_line(
                "captioning: %s", format_boolean(health.captioning if health else None)
            )
            write_stdout_line(
                "transcript lines: %s",
                health.transcript_lines if health and health.transcript_lines else 0,
            )
            write_stdout_line(
                "manual action: %s", format_boolean(bool(health and health.manual_action))
            )
            if health and health.manual_action:
                write_stdout_line("manual reason: %s", format_optional(health.manual_action.reason))
                write_stdout_line(
                    "manual message: %s", format_optional(health.manual_action.message)
                )
