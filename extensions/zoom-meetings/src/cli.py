"""CLI command registration and routing for Zoom Meetings."""

from __future__ import annotations

import argparse
from typing import Any

from .cli_runtime_commands import (
    handle_doctor_cli,
    handle_join_cli,
    handle_leave_cli,
    handle_setup_cli,
    handle_speak_cli,
    handle_status_cli,
    handle_transcript_cli,
)
from .cli_shared import add_json_flag


def register_zoom_meetings_cli(
    subparsers: argparse._SubParsersAction[Any],
) -> argparse.ArgumentParser:
    """Register the `zoommeetings` command tree onto the CLI subparsers."""
    parser = subparsers.add_parser(
        "zoommeetings",
        help="Zoom Meetings management and participation",
    )
    cmd_sub = parser.add_subparsers(dest="zoommeetings_action", required=True)

    # setup
    setup_p = cmd_sub.add_parser("setup", help="Verify Zoom Meetings readiness and prerequisites")
    add_json_flag(setup_p)
    setup_p.set_defaults(handler=handle_setup_cli)

    # join
    join_p = cmd_sub.add_parser("join", help="Join a Zoom meeting as guest via Web Client")
    join_p.add_argument(
        "url", nargs="?", help="Zoom meeting URL (e.g. https://zoom.us/j/123456789)"
    )
    join_p.add_argument("--url", dest="meeting_url", help="Zoom meeting URL override")
    join_p.add_argument("--name", "-n", help="Guest display name")
    join_p.add_argument("--passcode", "-p", help="Meeting passcode")
    join_p.add_argument(
        "--mode", choices=["agent", "bidi", "listen", "transcribe"], help="Participation mode"
    )
    add_json_flag(join_p)
    join_p.set_defaults(handler=handle_join_cli)

    # leave
    leave_p = cmd_sub.add_parser("leave", help="Leave an active Zoom meeting session")
    leave_p.add_argument("session_id", nargs="?", help="Zoom meeting session ID")
    add_json_flag(leave_p)
    leave_p.set_defaults(handler=handle_leave_cli)

    # status
    status_p = cmd_sub.add_parser("status", help="Inspect active Zoom meeting session status")
    status_p.add_argument("session_id", nargs="?", help="Zoom meeting session ID")
    add_json_flag(status_p)
    status_p.set_defaults(handler=handle_status_cli)

    # transcript
    trans_p = cmd_sub.add_parser(
        "transcript", help="Retrieve captions/transcript for a Zoom meeting"
    )
    trans_p.add_argument("session_id", nargs="?", help="Zoom meeting session ID")
    add_json_flag(trans_p)
    trans_p.set_defaults(handler=handle_transcript_cli)

    # speak
    speak_p = cmd_sub.add_parser("speak", help="Speak a message into an active Zoom meeting")
    speak_p.add_argument("session_id", nargs="?", help="Zoom meeting session ID")
    speak_p.add_argument("--message", "-m", required=True, help="Message text to speak")
    add_json_flag(speak_p)
    speak_p.set_defaults(handler=handle_speak_cli)

    # doctor
    doc_p = cmd_sub.add_parser("doctor", help="Inspect and repair Zoom Meetings configuration")
    doc_p.add_argument(
        "--fix", action="store_true", help="Automatically repair legacy/invalid config"
    )
    add_json_flag(doc_p)
    doc_p.set_defaults(handler=handle_doctor_cli)

    return parser
