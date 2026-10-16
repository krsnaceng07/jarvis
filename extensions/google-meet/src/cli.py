"""Google Meet extension CLI registration and unified subcommand dispatcher."""

from __future__ import annotations

import argparse
from typing import Callable

from .cli_artifact_commands import (
    handle_artifacts_command,
    handle_attendance_command,
    handle_export_command,
)
from .cli_command_context import GoogleMeetCliContext
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
from .cli_shared import write_output
from .cli_space_commands import (
    handle_calendar_events_command,
    handle_create_command,
    handle_end_active_conference_command,
    handle_preflight_command,
    handle_resolve_space_command,
)
from .oauth import perform_google_meet_oauth_flow, refresh_google_meet_oauth_token


async def handle_auth_login_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet auth login` CLI subcommand."""
    client_id = getattr(args, "client_id", None) or (
        ctx.config.get("oauth", {}).get("clientId") if isinstance(ctx.config, dict) else None
    )
    client_secret = getattr(args, "client_secret", None) or (
        ctx.config.get("oauth", {}).get("clientSecret") if isinstance(ctx.config, dict) else None
    )

    if not client_id:
        write_output(
            ctx,
            {"error": "Missing OAuth client_id. Provide --client-id or configure oauth.clientId."},
            is_error=True,
        )
        return 1

    flow_res = await perform_google_meet_oauth_flow(
        client_id=client_id,
        client_secret=client_secret,
        manual_code_prompt=getattr(args, "manual_code", False),
    )
    if not flow_res.is_ok:
        write_output(ctx, {"error": str(flow_res.error)}, is_error=True)
        return 1

    oauth_creds = flow_res.unwrap()
    write_output(
        ctx,
        {
            "success": True,
            "message": "OAuth authentication successful.",
            "tokens": {
                "access_token": oauth_creds.access_token[:8] + "..."
                if oauth_creds.access_token
                else None,
                "refresh_token": "PRESENT" if oauth_creds.refresh_token else "NONE",
                "expires_at": oauth_creds.expires_at,
                "scopes": oauth_creds.scopes,
            },
        },
    )
    return 0


async def handle_auth_refresh_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet auth refresh` CLI subcommand."""
    client_id = getattr(args, "client_id", None) or (
        ctx.config.get("oauth", {}).get("clientId") if isinstance(ctx.config, dict) else None
    )
    client_secret = getattr(args, "client_secret", None) or (
        ctx.config.get("oauth", {}).get("clientSecret") if isinstance(ctx.config, dict) else None
    )
    refresh_token = (
        ctx.config.get("oauth", {}).get("refreshToken") if isinstance(ctx.config, dict) else None
    )

    if not client_id or not refresh_token:
        write_output(ctx, {"error": "OAuth clientId and refreshToken required."}, is_error=True)
        return 1

    refresh_res = await refresh_google_meet_oauth_token(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )
    if not refresh_res.is_ok:
        write_output(ctx, {"error": str(refresh_res.error)}, is_error=True)
        return 1

    creds = refresh_res.unwrap()
    write_output(
        ctx,
        {
            "success": True,
            "message": "OAuth token refreshed.",
            "tokens": {
                "access_token": creds.access_token[:8] + "..." if creds.access_token else None,
                "expires_at": creds.expires_at,
                "scopes": creds.scopes,
            },
        },
    )
    return 0


def register_google_meet_cli(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    context_factory: Callable[[], GoogleMeetCliContext],
) -> None:
    """Register all `googlemeet` subcommands into a CLI argument parser."""
    meet_parser = subparsers.add_parser(
        "googlemeet",
        help="Google Meet automation, space management, transcripts, attendance, and live audio participation.",
    )
    meet_parser.add_argument("--json", action="store_true", help="Format output as JSON.")
    meet_subparsers = meet_parser.add_subparsers(dest="meet_subcommand", required=True)

    # 1. doctor
    doc_parser = meet_subparsers.add_parser(
        "doctor", help="Inspect and repair Google Meet configuration and dependencies."
    )
    doc_parser.add_argument(
        "--fix", action="store_true", help="Apply automatic fixes where possible."
    )
    doc_parser.set_defaults(handler=handle_doctor_command)

    # 2. auth
    auth_parser = meet_subparsers.add_parser("auth", help="Manage Google Meet OAuth credentials.")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_subcommand", required=True)

    login_p = auth_subparsers.add_parser("login", help="Start OAuth PKCE flow to acquire tokens.")
    login_p.add_argument("--client-id", type=str, help="Google OAuth Client ID.")
    login_p.add_argument("--client-secret", type=str, help="Google OAuth Client Secret (optional).")
    login_p.add_argument(
        "--manual-code",
        action="store_true",
        help="Manually paste auth code instead of loopback server.",
    )
    login_p.set_defaults(handler=handle_auth_login_command)

    refresh_p = auth_subparsers.add_parser("refresh", help="Refresh existing OAuth tokens.")
    refresh_p.add_argument("--client-id", type=str, help="Google OAuth Client ID.")
    refresh_p.add_argument("--client-secret", type=str, help="Google OAuth Client Secret.")
    refresh_p.set_defaults(handler=handle_auth_refresh_command)

    # 3. create
    create_p = meet_subparsers.add_parser("create", help="Create a new Google Meet space.")
    create_p.add_argument("--join", action="store_true", help="Immediately join created space.")
    create_p.add_argument(
        "--mode", type=str, choices=["agent", "bidi", "listen_only", "passive"], help="Join mode."
    )
    create_p.add_argument(
        "--transport", type=str, choices=["chrome", "twilio"], help="Participation transport."
    )
    create_p.add_argument("--audio-in", type=str, help="Input audio device.")
    create_p.add_argument("--audio-out", type=str, help="Output audio device.")
    create_p.add_argument("--profile", type=str, help="Chrome browser profile name.")
    create_p.add_argument("--node", type=str, help="Node ID for remote execution.")
    create_p.add_argument(
        "--access-type", type=str, choices=["OPEN", "TRUSTED", "RESTRICTED"], help="Access policy."
    )
    create_p.set_defaults(handler=handle_create_command)

    # 4. end-active-conference
    end_p = meet_subparsers.add_parser(
        "end-active-conference", help="End the active conference for a space."
    )
    end_p.add_argument("target", type=str, help="Space name or Meet URL.")
    end_p.set_defaults(handler=handle_end_active_conference_command)

    # 5. resolve-space
    res_p = meet_subparsers.add_parser(
        "resolve-space", help="Resolve space metadata from target or URL."
    )
    res_p.add_argument("target", type=str, help="Space name or Meet URL.")
    res_p.set_defaults(handler=handle_resolve_space_command)

    # 6. preflight
    pre_p = meet_subparsers.add_parser(
        "preflight", help="Check readiness, tokens, and scopes for Google Meet."
    )
    pre_p.add_argument("target", type=str, nargs="?", help="Optional space name or Meet URL.")
    pre_p.set_defaults(handler=handle_preflight_command)

    # 7. calendar-events
    cal_p = meet_subparsers.add_parser(
        "calendar-events", help="List upcoming calendar events with Meet links."
    )
    cal_p.add_argument("--limit", type=int, default=10, help="Maximum events to return.")
    cal_p.add_argument("--time-min", type=str, help="Start ISO timestamp.")
    cal_p.add_argument("--time-max", type=str, help="End ISO timestamp.")
    cal_p.set_defaults(handler=handle_calendar_events_command)

    # 8. artifacts
    art_p = meet_subparsers.add_parser(
        "artifacts", help="Fetch recordings, transcripts, and smart notes."
    )
    art_p.add_argument("target", type=str, help="Conference record name, space name, or Meet URL.")
    art_p.set_defaults(handler=handle_artifacts_command)

    # 9. attendance
    att_p = meet_subparsers.add_parser("attendance", help="Calculate meeting attendance metrics.")
    att_p.add_argument("target", type=str, help="Conference record name, space name, or Meet URL.")
    att_p.add_argument(
        "--late-threshold-seconds", type=int, default=300, help="Late threshold in seconds."
    )
    att_p.add_argument(
        "--early-leave-threshold-seconds",
        type=int,
        default=300,
        help="Early leave threshold in seconds.",
    )
    att_p.add_argument(
        "--format", type=str, choices=["json", "csv", "md"], default="json", help="Output format."
    )
    att_p.set_defaults(handler=handle_attendance_command)

    # 10. export
    exp_p = meet_subparsers.add_parser(
        "export", help="Export meeting artifacts and attendance into a bundle."
    )
    exp_p.add_argument("target", type=str, help="Conference record name, space name, or Meet URL.")
    exp_p.add_argument("--output", type=str, help="Output destination file or directory path.")
    exp_p.add_argument(
        "--format", type=str, choices=["zip", "dir"], default="zip", help="Bundle format."
    )
    exp_p.add_argument(
        "--no-drive", action="store_true", help="Skip Google Drive file content fetching."
    )
    exp_p.set_defaults(handler=handle_export_command)

    # 11. join
    join_p = meet_subparsers.add_parser("join", help="Join a Google Meet room.")
    join_p.add_argument("target", type=str, help="Meet URL or space ID.")
    join_p.add_argument(
        "--mode",
        type=str,
        choices=["agent", "bidi", "listen_only", "passive", "transcribe", "realtime"],
        help="Join mode.",
    )
    join_p.add_argument(
        "--transport",
        type=str,
        choices=["chrome", "chrome-node", "twilio"],
        help="Participation transport.",
    )
    join_p.add_argument("--dial-in-number", type=str, help="Twilio dial-in phone number.")
    join_p.add_argument("--pin", type=str, help="Meeting PIN.")
    join_p.add_argument("--dtmf-sequence", type=str, help="DTMF sequence.")
    join_p.add_argument("--message", type=str, help="Initial greeting message.")
    join_p.add_argument("--audio-in", type=str, help="Audio input device.")
    join_p.add_argument("--audio-out", type=str, help="Audio output device.")
    join_p.add_argument("--profile", type=str, help="Chrome browser profile.")
    join_p.add_argument("--node", type=str, help="Node ID.")
    join_p.set_defaults(handler=handle_join_command)

    # 12. leave
    leave_p = meet_subparsers.add_parser("leave", help="Leave active meeting session.")
    leave_p.add_argument("session_id", nargs="?", type=str, help="Target session ID.")
    leave_p.add_argument(
        "--session-id", dest="session_id_flag", type=str, help="Target session ID."
    )
    leave_p.set_defaults(handler=handle_leave_command)

    # 13. speak
    speak_p = meet_subparsers.add_parser("speak", help="Speak text in active meeting.")
    speak_p.add_argument("text", type=str, help="Text to speak.")
    speak_p.add_argument("--session-id", type=str, help="Target session ID.")
    speak_p.set_defaults(handler=handle_speak_command)

    # 14. status
    stat_p = meet_subparsers.add_parser(
        "status", help="Get active meeting and audio health status."
    )
    stat_p.add_argument("session_id", nargs="?", type=str, help="Target session ID.")
    stat_p.add_argument("--session-id", dest="session_id_flag", type=str, help="Target session ID.")
    stat_p.set_defaults(handler=handle_status_command)

    # 15. transcript
    trans_p = meet_subparsers.add_parser(
        "transcript", help="Fetch realtime meeting transcript lines."
    )
    trans_p.add_argument("session_id", nargs="?", type=str, help="Target session ID.")
    trans_p.add_argument(
        "--session-id", dest="session_id_flag", type=str, help="Target session ID."
    )
    trans_p.add_argument("--limit", type=int, default=50, help="Max transcript lines.")
    trans_p.set_defaults(handler=handle_transcript_command)

    # 16. recover-tab
    rec_p = meet_subparsers.add_parser("recover-tab", help="Recover Chrome tab from browser proxy.")
    rec_p.add_argument("target", nargs="?", type=str, help="Optional Meet URL to recover/inspect.")
    rec_p.add_argument(
        "--transport",
        type=str,
        choices=["chrome", "chrome-node"],
        help="Browser transport.",
    )
    rec_p.add_argument("--profile", type=str, help="Browser profile.")
    rec_p.add_argument("--node", type=str, help="Node ID.")
    rec_p.set_defaults(handler=handle_recover_tab_command)

    # 17. test-speech
    ts_p = meet_subparsers.add_parser("test-speech", help="Run speech playback probe.")
    ts_p.add_argument("target", nargs="?", type=str, help="Meet URL to join for speech test.")
    ts_p.add_argument(
        "--message",
        "--text",
        dest="text",
        type=str,
        default="Say exactly: Google Meet speech test complete.",
        help="Probe speech text.",
    )
    ts_p.add_argument(
        "--transport",
        type=str,
        choices=["chrome", "chrome-node", "twilio"],
        help="Participation transport.",
    )
    ts_p.add_argument(
        "--mode",
        type=str,
        choices=["agent", "bidi"],
        default="agent",
        help="Speech mode.",
    )
    ts_p.add_argument("--dial-in-number", type=str, help="Twilio dial-in phone number.")
    ts_p.add_argument("--pin", type=str, help="Meeting PIN.")
    ts_p.add_argument("--audio-out", type=str, help="Audio output device.")
    ts_p.add_argument("--profile", type=str, help="Chrome browser profile.")
    ts_p.add_argument("--node", type=str, help="Node ID.")
    ts_p.set_defaults(handler=handle_test_speech_command)

    # 18. test-listen
    tl_p = meet_subparsers.add_parser("test-listen", help="Run microphone capture probe.")
    tl_p.add_argument("target", nargs="?", type=str, help="Meet URL to join for caption probe.")
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

    # 19. setup
    setup_p = meet_subparsers.add_parser("setup", help="Validate runtime devices and node setup.")
    setup_p.add_argument(
        "--transport",
        type=str,
        choices=["chrome", "chrome-node", "twilio"],
        help="Filter checks by transport.",
    )
    setup_p.add_argument("--mode", type=str, help="Filter checks by mode.")
    setup_p.add_argument("--dial-in-number", type=str, help="Twilio dial-in phone number.")
    setup_p.add_argument("--node", type=str, help="Node ID.")
    setup_p.set_defaults(handler=handle_setup_command)
