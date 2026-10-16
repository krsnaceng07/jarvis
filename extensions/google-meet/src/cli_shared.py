"""Shared formatting, parsing, and execution routines for Google Meet CLI commands."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from .transports.types import GoogleMeetSession


def parse_google_meet_mode(value: str | None) -> str | None:
    if value in (None, "agent", "bidi", "transcribe", "realtime"):
        return value
    raise ValueError(f"mode must be agent, bidi, transcribe, or realtime; received {value}")


def parse_google_meet_transport(value: str | None) -> str | None:
    if value in (None, "chrome", "chrome-node", "twilio"):
        return value
    raise ValueError(f"transport must be chrome, chrome-node, or twilio; received {value}")


def parse_google_meet_browser_transport(value: str | None) -> str | None:
    transport = parse_google_meet_transport(value)
    if transport == "twilio":
        raise ValueError(f"transport must be chrome or chrome-node; received {value}")
    return transport


def write_stdout_json(value: Any) -> None:
    if hasattr(value, "__dict__"):
        val_dict = getattr(value, "__dict__")
        sys.stdout.write(f"{json.dumps(val_dict, indent=2, default=str)}\n")
    else:
        sys.stdout.write(f"{json.dumps(value, indent=2, default=str)}\n")
    sys.stdout.flush()


def write_output(ctx: Any, payload: Any, is_error: bool = False) -> None:
    """Format and write CLI output according to JSON mode or standard output."""
    json_mode = getattr(ctx, "json_mode", False)
    if json_mode or is_error or isinstance(payload, (dict, list)):
        write_stdout_json(payload)
    else:
        write_stdout_line("%s", payload)


def format_dict(d: dict[str, Any]) -> str:
    return json.dumps(d, indent=2, default=str)


def write_stdout_line(fmt: str, *args: Any) -> None:
    if args:
        try:
            sys.stdout.write(f"{fmt % args}\n")
        except Exception:
            sys.stdout.write(f"{fmt.format(*args)}\n")
    else:
        sys.stdout.write(f"{fmt}\n")
    sys.stdout.flush()


async def write_cli_output(options: dict[str, Any], text: str) -> None:
    output_path = options.get("output")
    if output_path and output_path.strip():
        out_file = output_path.strip()
        os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(text if text.endswith("\n") else f"{text}\n")
        write_stdout_line("wrote: %s", out_file)
        return
    sys.stdout.write(text if text.endswith("\n") else f"{text}\n")
    sys.stdout.flush()


def prompt_input(message: str) -> str:
    return input(message)


def parse_optional_number(value: Any) -> int | float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        val_str = str(value).strip()
        if "." in val_str:
            return float(val_str)
        return int(val_str)
    except Exception as err:
        raise ValueError(f"Expected a numeric value, received {value}") from err


def parse_positive_number(value: Any, label: str) -> int | float | None:
    if value is None or str(value).strip() == "":
        return None
    num = parse_optional_number(value)
    if num is None or num <= 0:
        raise ValueError(f"{label} must be a positive number")
    return num


def parse_positive_integer_option(value: Any, label: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        num = int(str(value).strip())
        if num <= 0:
            raise ValueError()
        return num
    except Exception as err:
        raise ValueError(f"{label} must be a positive integer") from err


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


def format_duration(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    seconds = int(round(value / 1000.0))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    rem_sec = seconds % 60
    if minutes < 60:
        return f"{minutes}m {rem_sec}s" if rem_sec else f"{minutes}m"
    hours = minutes // 60
    rem_min = minutes % 60
    return f"{hours}h {rem_min}m" if rem_min else f"{hours}h"


def write_setup_status(status: Any) -> None:
    is_ok = getattr(status, "ok", False)
    write_stdout_line("Google Meet setup: %s", "OK" if is_ok else "needs attention")
    checks = getattr(status, "checks", [])
    for check in checks:
        c_ok = getattr(check, "ok", False)
        c_id = getattr(check, "id", "")
        c_msg = getattr(check, "message", "")
        write_stdout_line("[%s] %s: %s", "ok" if c_ok else "fail", c_id, c_msg)


def write_doctor_status(status: Any) -> None:
    if not status:
        write_stdout_line("Google Meet session: not found")
        return

    sessions = (
        status
        if isinstance(status, list)
        else ([status] if isinstance(status, GoogleMeetSession) else [])
    )
    if not sessions:
        write_stdout_line("Google Meet sessions: none")
        return

    write_stdout_line("Google Meet sessions: %d", len(sessions))
    for session in sessions:
        health = session.chrome.health if session.chrome else None
        write_stdout_line("")
        write_stdout_line("session: %s", session.id)
        write_stdout_line("url: %s", session.url)
        write_stdout_line("state: %s", session.state)
        write_stdout_line("transport: %s", session.transport)
        write_stdout_line("mode: %s", session.mode)
        if session.twilio:
            write_stdout_line("twilio dial-in: %s", session.twilio.dial_in_number)
            write_stdout_line("voice call id: %s", format_optional(session.twilio.voice_call_id))
            write_stdout_line("dtmf sent: %s", format_boolean(session.twilio.dtmf_sent))
            write_stdout_line("intro sent: %s", format_boolean(session.twilio.intro_sent))
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
                "last caption: %s", format_optional(health.last_caption_at if health else None)
            )
            write_stdout_line(
                "manual action: %s", format_boolean(bool(health and health.manual_action))
            )
            if health and health.manual_action:
                write_stdout_line("manual reason: %s", format_optional(health.manual_action.reason))
                write_stdout_line(
                    "manual message: %s", format_optional(health.manual_action.message)
                )
            if health and health.last_caption_text:
                speaker = f"{health.last_caption_speaker}: " if health.last_caption_speaker else ""
                write_stdout_line("last caption text: %s%s", speaker, health.last_caption_text)


def write_recover_current_tab_result(result: dict[str, Any]) -> None:
    found = result.get("found", False)
    write_stdout_line("Google Meet current tab: %s", "found" if found else "not found")
    write_stdout_line("transport: %s", result.get("transport", "chrome"))
    write_stdout_line("node: %s", result.get("node_id") or "local/none")
    if result.get("target_id"):
        write_stdout_line("target: %s", result["target_id"])
    tab = result.get("tab")
    if tab and getattr(tab, "url", None):
        write_stdout_line("tab url: %s", tab.url)
    write_stdout_line("message: %s", result.get("message", ""))


def write_leave_result(session_id: str, result: dict[str, Any]) -> None:
    if result.get("browser_left") is False:
        write_stdout_line(
            "left %s, but the browser participant may still be in the call; check session notes",
            session_id,
        )
        return
    write_stdout_line("left %s", session_id)


async def call_google_meet_gateway(params: dict[str, Any]) -> dict[str, Any]:
    call_gw = params.get("callGateway")
    method = params.get("method")
    payload = params.get("payload")
    if call_gw:
        try:
            res = await call_gw(method, payload)
            return {"ok": True, "payload": res}
        except Exception as err:
            return {"ok": False, "error": err}
    return {"ok": False, "error": "Gateway unavailable"}
