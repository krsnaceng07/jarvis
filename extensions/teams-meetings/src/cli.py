"""Teams Meetings extension CLI registration and unified subcommand dispatcher."""

from __future__ import annotations

import argparse
from typing import Callable

from .cli_command_context import TeamsMeetingsCliContext
from .cli_doctor import handle_doctor_command
from .cli_runtime_commands import (
    handle_join_command,
    handle_leave_command,
    handle_recover_tab_command,
    handle_setup_command,
    handle_speak_command,
    handle_status_command,
    handle_test_listen_command,
    handle_test_speech_command,
    handle_transcript_command,
)


def register_teams_meetings_cli(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    context_factory: Callable[[], TeamsMeetingsCliContext],
) -> None:
    """Register all `teamsmeetings` subcommands into a CLI argument parser."""
    teams_parser = subparsers.add_parser(
        "teamsmeetings",
        help="Microsoft Teams meeting automation, transcripts, and browser participation.",
    )
    teams_parser.add_argument("--json", action="store_true", help="Format output as JSON.")
    teams_subparsers = teams_parser.add_subparsers(dest="teams_subcommand", required=True)

    # 1. doctor
    doc_parser = teams_subparsers.add_parser(
        "doctor", help="Inspect and repair Teams Meetings configuration and health."
    )
    doc_parser.add_argument("session_id", nargs="?", help="Teams session ID.")
    doc_parser.add_argument(
        "--fix", action="store_true", help="Apply automatic fixes where possible."
    )
    doc_parser.set_defaults(handler=handle_doctor_command)

    # 2. join
    join_p = teams_subparsers.add_parser("join", help="Join a Microsoft Teams room.")
    join_p.add_argument("target", type=str, help="Teams meeting URL.")
    join_p.add_argument(
        "--mode",
        type=str,
        choices=["agent", "bidi", "transcribe", "realtime"],
        help="Join mode.",
    )
    join_p.add_argument(
        "--transport",
        type=str,
        choices=["chrome", "chrome-node"],
        help="Participation transport.",
    )
    join_p.add_argument("--message", type=str, help="Initial greeting message.")
    join_p.add_argument("--audio-in", type=str, help="Audio input device.")
    join_p.add_argument("--audio-out", type=str, help="Audio output device.")
    join_p.add_argument("--profile", type=str, help="Chrome browser profile.")
    join_p.add_argument("--node", type=str, help="Node ID.")
    join_p.set_defaults(handler=handle_join_command)

    # 3. leave
    leave_p = teams_subparsers.add_parser("leave", help="Leave active Teams meeting session.")
    leave_p.add_argument("session_id", nargs="?", type=str, help="Target session ID.")
    leave_p.add_argument(
        "--session-id", dest="session_id_flag", type=str, help="Target session ID."
    )
    leave_p.set_defaults(handler=handle_leave_command)

    # 4. speak
    speak_p = teams_subparsers.add_parser("speak", help="Speak text in active Teams meeting.")
    speak_p.add_argument("text", type=str, help="Text to speak.")
    speak_p.add_argument("--session-id", type=str, help="Target session ID.")
    speak_p.set_defaults(handler=handle_speak_command)

    # 5. status
    stat_p = teams_subparsers.add_parser(
        "status", help="Get active Teams meeting and audio health status."
    )
    stat_p.add_argument("session_id", nargs="?", type=str, help="Target session ID.")
    stat_p.add_argument("--session-id", dest="session_id_flag", type=str, help="Target session ID.")
    stat_p.set_defaults(handler=handle_status_command)

    # 6. transcript
    trans_p = teams_subparsers.add_parser(
        "transcript", help="Fetch realtime Teams meeting transcript lines."
    )
    trans_p.add_argument("session_id", nargs="?", type=str, help="Target session ID.")
    trans_p.add_argument(
        "--session-id", dest="session_id_flag", type=str, help="Target session ID."
    )
    trans_p.add_argument("--limit", type=int, default=50, help="Max transcript lines.")
    trans_p.set_defaults(handler=handle_transcript_command)

    # 7. recover-tab
    rec_p = teams_subparsers.add_parser("recover-tab", help="Recover Teams tab from browser proxy.")
    rec_p.add_argument("target", nargs="?", type=str, help="Optional Teams URL to recover/inspect.")
    rec_p.add_argument(
        "--transport",
        type=str,
        choices=["chrome", "chrome-node"],
        help="Browser transport.",
    )
    rec_p.add_argument("--profile", type=str, help="Browser profile.")
    rec_p.add_argument("--node", type=str, help="Node ID.")
    rec_p.set_defaults(handler=handle_recover_tab_command)

    # 8. test-speech
    ts_p = teams_subparsers.add_parser("test-speech", help="Run speech playback probe.")
    ts_p.add_argument("target", nargs="?", type=str, help="Teams URL to join for speech test.")
    ts_p.add_argument(
        "--message",
        "--text",
        dest="text",
        type=str,
        default="Say exactly: Microsoft Teams speech test complete.",
        help="Probe speech text.",
    )
    ts_p.add_argument(
        "--transport",
        type=str,
        choices=["chrome", "chrome-node"],
        help="Participation transport.",
    )
    ts_p.add_argument(
        "--mode",
        type=str,
        choices=["agent", "bidi"],
        default="agent",
        help="Speech mode.",
    )
    ts_p.add_argument("--audio-out", type=str, help="Audio output device.")
    ts_p.add_argument("--profile", type=str, help="Chrome browser profile.")
    ts_p.add_argument("--node", type=str, help="Node ID.")
    ts_p.set_defaults(handler=handle_test_speech_command)

    # 9. test-listen
    tl_p = teams_subparsers.add_parser("test-listen", help="Run microphone capture probe.")
    tl_p.add_argument("target", nargs="?", type=str, help="Teams URL to join for caption probe.")
    tl_p.add_argument(
        "--transport",
        type=str,
        choices=["chrome", "chrome-node"],
        help="Participation transport.",
    )
    tl_p.add_argument("--duration", type=float, default=5.0, help="Duration in seconds.")
    tl_p.add_argument("--audio-in", type=str, help="Audio input device.")
    tl_p.add_argument("--profile", type=str, help="Chrome browser profile.")
    tl_p.add_argument("--node", type=str, help="Node ID.")
    tl_p.set_defaults(handler=handle_test_listen_command)

    # 10. setup
    setup_p = teams_subparsers.add_parser("setup", help="Validate runtime devices and node setup.")
    setup_p.add_argument(
        "--transport",
        type=str,
        choices=["chrome", "chrome-node"],
        help="Filter checks by transport.",
    )
    setup_p.add_argument("--mode", type=str, help="Filter checks by mode.")
    setup_p.add_argument("--node", type=str, help="Node ID.")
    setup_p.set_defaults(handler=handle_setup_command)
