"""CLI runtime command execution handlers for Zoom Meetings."""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from .cli_shared import print_cli_result
from .config import ZoomMeetingsConfig, resolve_zoom_meetings_config
from .doctor import run_zoom_meetings_doctor
from .runtime import ZoomMeetingsRuntime
from .setup import get_zoom_meetings_setup_status


def _get_runtime(raw_config: dict[str, Any] | None) -> ZoomMeetingsRuntime:
    cfg_res = resolve_zoom_meetings_config(raw_config)
    cfg = cfg_res.unwrap() if cfg_res.is_ok else ZoomMeetingsConfig()
    return ZoomMeetingsRuntime(cfg)


def handle_setup_cli(args: argparse.Namespace, raw_config: dict[str, Any] | None = None) -> int:
    """Handle `jarvis zoommeetings setup [--json]`."""
    cfg_res = resolve_zoom_meetings_config(raw_config)
    cfg = cfg_res.unwrap() if cfg_res.is_ok else ZoomMeetingsConfig()
    status = get_zoom_meetings_setup_status(cfg)

    is_json = getattr(args, "json", False)
    if is_json:
        out = {
            "ok": status.ok,
            "checks": [{"id": c.id, "ok": c.ok, "message": c.message} for c in status.checks],
        }
        print_cli_result(out, is_json=True)
    else:
        print("=== Zoom Meetings Setup ===")
        print(f"Readiness: {'READY' if status.ok else 'INCOMPLETE'}\n")
        for c in status.checks:
            mark = "✓" if c.ok else "✗"
            print(f" [{mark}] {c.id}: {c.message}")

    return 0 if status.ok else 1


def handle_join_cli(args: argparse.Namespace, raw_config: dict[str, Any] | None = None) -> int:
    """Handle `jarvis zoommeetings join <url> [--name <name>] [--passcode <pwd>] [--mode <mode>]`."""
    runtime = _get_runtime(raw_config)
    url = getattr(args, "url", None) or getattr(args, "meeting_url", None)
    name = getattr(args, "name", None) or getattr(args, "guest_name", None)
    passcode = getattr(args, "passcode", None)
    mode = getattr(args, "mode", None)
    is_json = getattr(args, "json", False)

    res = asyncio.run(
        runtime.join(
            url=url,
            guest_name=name,
            passcode=passcode,
            mode=mode,
        )
    )

    if not res.is_ok:
        err = {"ok": False, "error": str(res.error)}
        print_cli_result(err, is_json=is_json)
        return 1

    val = res.unwrap()
    out = {
        "ok": val.ok,
        "sessionId": val.session_id,
        "status": val.status,
        "manualAction": val.manual_action,
        "manualActionReason": val.manual_action_reason,
        "manualActionMessage": val.manual_action_message,
    }
    print_cli_result(out, is_json=is_json)
    return 0


def handle_leave_cli(args: argparse.Namespace, raw_config: dict[str, Any] | None = None) -> int:
    """Handle `jarvis zoommeetings leave [sessionId]`."""
    runtime = _get_runtime(raw_config)
    session_id = getattr(args, "session_id", None) or getattr(args, "sessionId", None)
    is_json = getattr(args, "json", False)

    res = asyncio.run(runtime.leave(session_id=session_id))
    if not res.is_ok:
        err = {"ok": False, "error": str(res.error)}
        print_cli_result(err, is_json=is_json)
        return 1

    print_cli_result({"ok": True, "sessionId": session_id, "status": "ended"}, is_json=is_json)
    return 0


def handle_status_cli(args: argparse.Namespace, raw_config: dict[str, Any] | None = None) -> int:
    """Handle `jarvis zoommeetings status [sessionId]`."""
    runtime = _get_runtime(raw_config)
    session_id = getattr(args, "session_id", None) or getattr(args, "sessionId", None)
    is_json = getattr(args, "json", False)

    res = asyncio.run(runtime.get_status(session_id=session_id))
    if not res.is_ok:
        err = {"ok": False, "error": str(res.error)}
        print_cli_result(err, is_json=is_json)
        return 1

    print_cli_result(res.unwrap(), is_json=is_json)
    return 0


def handle_transcript_cli(
    args: argparse.Namespace, raw_config: dict[str, Any] | None = None
) -> int:
    """Handle `jarvis zoommeetings transcript [sessionId]`."""
    runtime = _get_runtime(raw_config)
    session_id = getattr(args, "session_id", None) or getattr(args, "sessionId", None)
    is_json = getattr(args, "json", False)

    res = asyncio.run(runtime.get_transcript(session_id=session_id))
    if not res.is_ok:
        err = {"ok": False, "error": str(res.error)}
        print_cli_result(err, is_json=is_json)
        return 1

    print_cli_result({"ok": True, "transcript": res.unwrap()}, is_json=is_json)
    return 0


def handle_speak_cli(args: argparse.Namespace, raw_config: dict[str, Any] | None = None) -> int:
    """Handle `jarvis zoommeetings speak [sessionId] --message <text>`."""
    runtime = _get_runtime(raw_config)
    session_id = getattr(args, "session_id", None) or getattr(args, "sessionId", None)
    message = getattr(args, "message", None) or getattr(args, "text", "")
    is_json = getattr(args, "json", False)

    res = asyncio.run(runtime.speak(text=message, session_id=session_id))
    if not res.is_ok:
        err = {"ok": False, "error": str(res.error)}
        print_cli_result(err, is_json=is_json)
        return 1

    print_cli_result(res.unwrap(), is_json=is_json)
    return 0


def handle_doctor_cli(args: argparse.Namespace, raw_config: dict[str, Any] | None = None) -> int:
    """Handle `jarvis zoommeetings doctor [--fix]`."""
    fix = getattr(args, "fix", False)
    is_json = getattr(args, "json", False)

    res = asyncio.run(run_zoom_meetings_doctor(raw_config, fix=fix))
    if not res.is_ok:
        err = {"ok": False, "error": str(res.error)}
        print_cli_result(err, is_json=is_json)
        return 1

    print_cli_result(res.unwrap(), is_json=is_json)
    return 0
