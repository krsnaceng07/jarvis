"""Unified CLI parser and command router for Voice Call."""

from __future__ import annotations

import argparse
from typing import Any

from .cli_doctor import handle_voice_call_doctor_cli
from .cli_runtime_commands import (
    handle_call_cli,
    handle_continue_cli,
    handle_dtmf_cli,
    handle_end_cli,
    handle_expose_cli,
    handle_latency_cli,
    handle_setup_cli,
    handle_smoke_cli,
    handle_speak_cli,
    handle_status_cli,
    handle_tail_cli,
)
from .cli_shared import add_json_flag


def register_voice_call_cli(subparsers: argparse._SubParsersAction[Any]) -> argparse.ArgumentParser:
    """Register the `voicecall` command tree onto the CLI subparsers."""
    parser = subparsers.add_parser(
        "voicecall",
        help="Voice Call management (Twilio, Telnyx, Plivo, Mock)",
    )
    cmd_sub = parser.add_subparsers(dest="voicecall_action", required=True)

    # setup
    setup_p = cmd_sub.add_parser("setup", help="Verify Voice Call configuration readiness")
    add_json_flag(setup_p)
    setup_p.set_defaults(handler=handle_setup_cli)

    # smoke
    smoke_p = cmd_sub.add_parser("smoke", help="Perform a smoke test call (dry run by default)")
    smoke_p.add_argument("--to", help="Target phone number (E.164)")
    smoke_p.add_argument("--yes", action="store_true", help="Place live call instead of dry run")
    add_json_flag(smoke_p)
    smoke_p.set_defaults(handler=handle_smoke_cli)

    # call / initiate
    call_p = cmd_sub.add_parser("call", help="Initiate an outbound telephone call")
    call_p.add_argument("to", nargs="?", help="Destination phone number (E.164)")
    call_p.add_argument("--to", dest="to_flag", help="Destination phone number (E.164)")
    call_p.add_argument("--from", dest="from_number", help="Caller ID phone number (E.164)")
    call_p.add_argument("--message", "-m", help="Initial greeting or message text")
    call_p.add_argument(
        "--mode", choices=["notify", "turn", "realtime", "streaming"], help="Audio mode"
    )
    call_p.add_argument("--agent", help="Owning agent ID")
    add_json_flag(call_p)
    call_p.set_defaults(handler=handle_call_cli)

    # start (alias for call)
    start_p = cmd_sub.add_parser(
        "start", help="Initiate an outbound telephone call (alias for call)"
    )
    start_p.add_argument("to", nargs="?", help="Destination phone number (E.164)")
    start_p.add_argument("--to", dest="to_flag", help="Destination phone number (E.164)")
    start_p.add_argument("--from", dest="from_number", help="Caller ID phone number (E.164)")
    start_p.add_argument("--message", "-m", help="Initial greeting or message text")
    start_p.add_argument(
        "--mode", choices=["notify", "turn", "realtime", "streaming"], help="Audio mode"
    )
    start_p.add_argument("--agent", help="Owning agent ID")
    start_p.add_argument("--dtmf-sequence", help="Pre-connect DTMF digits (conversation mode only)")
    add_json_flag(start_p)
    start_p.set_defaults(handler=handle_call_cli)

    # continue
    cont_p = cmd_sub.add_parser("continue", help="Continue a multi-turn conversation")
    cont_p.add_argument("call_id", nargs="?", help="Active call session ID")
    cont_p.add_argument("--call-id", dest="call_id_flag", help="Active call session ID")
    cont_p.add_argument("--message", "-m", required=True, help="Agent reply message")
    add_json_flag(cont_p)
    cont_p.set_defaults(handler=handle_continue_cli)

    # speak
    speak_p = cmd_sub.add_parser("speak", help="Speak a text message into an active call")
    speak_p.add_argument("call_id", nargs="?", help="Active call session ID")
    speak_p.add_argument("--call-id", dest="call_id_flag", help="Active call session ID")
    speak_p.add_argument("--message", "-m", dest="message_flag", help="Message text")
    speak_p.add_argument("--text", "-t", help="Text to speak")
    add_json_flag(speak_p)
    speak_p.set_defaults(handler=handle_speak_cli)

    # dtmf
    dtmf_p = cmd_sub.add_parser("dtmf", help="Send DTMF tones into an active call")
    dtmf_p.add_argument("call_id", nargs="?", help="Active call session ID")
    dtmf_p.add_argument("--call-id", dest="call_id_flag", help="Active call session ID")
    dtmf_p.add_argument("--digits", "-d", required=True, help="DTMF digits to transmit")
    add_json_flag(dtmf_p)
    dtmf_p.set_defaults(handler=handle_dtmf_cli)

    # end
    end_p = cmd_sub.add_parser("end", help="Terminate an active call")
    end_p.add_argument("call_id", nargs="?", help="Active call session ID")
    end_p.add_argument("--call-id", dest="call_id_flag", help="Active call session ID")
    add_json_flag(end_p)
    end_p.set_defaults(handler=handle_end_cli)

    # status
    status_p = cmd_sub.add_parser("status", help="Get call session status")
    status_p.add_argument("call_id", nargs="?", help="Call session ID")
    status_p.add_argument("--call-id", dest="call_id_flag", help="Call session ID")
    status_p.add_argument("--phone", help="Filter by phone number")
    add_json_flag(status_p)
    status_p.set_defaults(handler=handle_status_cli)

    # tail
    tail_p = cmd_sub.add_parser("tail", help="Tail recent live call turns and transcripts")
    tail_p.add_argument("call_id", nargs="?", help="Call session ID")
    tail_p.add_argument("--call-id", dest="call_id_flag", help="Call session ID")
    tail_p.add_argument("--last", type=int, default=20, help="Number of turns to show")
    add_json_flag(tail_p)
    tail_p.set_defaults(handler=handle_tail_cli)

    # latency
    latency_p = cmd_sub.add_parser(
        "latency", help="Summarize turn latency and listen-wait times from logs"
    )
    latency_p.add_argument("--file", help="Path to JSONL call log file")
    latency_p.add_argument("--last", type=int, default=200, help="Limit analysis to last N records")
    add_json_flag(latency_p)
    latency_p.set_defaults(handler=handle_latency_cli)

    # expose
    expose_p = cmd_sub.add_parser("expose", help="Expose local webhook via public tunnel or Funnel")
    expose_p.add_argument(
        "--mode", choices=["funnel", "tunnel"], default="funnel", help="Exposure mode"
    )
    add_json_flag(expose_p)
    expose_p.set_defaults(handler=handle_expose_cli)

    # doctor
    doc_p = cmd_sub.add_parser("doctor", help="Inspect and repair Voice Call configuration")
    doc_p.add_argument(
        "--fix", action="store_true", help="Automatically repair legacy/invalid config"
    )
    add_json_flag(doc_p)
    doc_p.set_defaults(handler=handle_voice_call_doctor_cli)

    return parser
