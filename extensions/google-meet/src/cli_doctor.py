"""Google Meet doctor subcommand implementation for checking session and OAuth health."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .cli_command_context import GoogleMeetCliCommandContext
from .cli_shared import (
    call_google_meet_gateway,
    parse_optional_number,
    write_doctor_status,
    write_stdout_json,
    write_stdout_line,
)
from .config import GoogleMeetConfig
from .meet import create_google_meet_space, fetch_google_meet_space
from .oauth import resolve_google_meet_access_token


@dataclass(slots=True)
class OAuthDoctorCheck:
    id: str
    ok: bool
    message: str


@dataclass(slots=True)
class OAuthDoctorReport:
    ok: bool
    configured: bool
    token_source: str | None = None
    expires_at: int | None = None
    meeting_uri: str | None = None
    created_space: str | None = None
    checks: list[OAuthDoctorCheck] = field(default_factory=list)


def sanitize_oauth_error_message(error: Any) -> str:
    msg = str(error)
    msg = re.sub(r'(access_token["\'=:\s]+)[^"\',\s&]+', r"\1[redacted]", msg, flags=re.IGNORECASE)
    msg = re.sub(r'(refresh_token["\'=:\s]+)[^"\',\s&]+', r"\1[redacted]", msg, flags=re.IGNORECASE)
    msg = re.sub(r'(client_secret["\'=:\s]+)[^"\',\s&]+', r"\1[redacted]", msg, flags=re.IGNORECASE)
    return msg


async def build_oauth_doctor_report(
    config: GoogleMeetConfig,
    options: dict[str, Any],
) -> OAuthDoctorReport:
    client_id = options.get("clientId") or config.oauth.client_id
    client_secret = options.get("clientSecret") or config.oauth.client_secret
    refresh_token = options.get("refreshToken") or config.oauth.refresh_token
    access_token = options.get("accessToken") or config.oauth.access_token
    expires_at = parse_optional_number(options.get("expiresAt")) or config.oauth.expires_at
    checks: list[OAuthDoctorCheck] = []

    has_refresh = bool(client_id and refresh_token)
    has_access = bool(access_token)
    if not has_refresh and not has_access:
        checks.append(
            OAuthDoctorCheck(
                id="oauth-config",
                ok=False,
                message="Missing Google Meet OAuth credentials. Configure oauth.clientId and oauth.refreshToken, or pass --client-id and --refresh-token.",
            )
        )
        return OAuthDoctorReport(ok=False, configured=False, checks=checks)

    checks.append(
        OAuthDoctorCheck(
            id="oauth-config",
            ok=True,
            message=(
                "Google Meet OAuth refresh credentials are configured"
                if has_refresh
                else "Google Meet cached access token is configured"
            ),
        )
    )

    token_obj = None
    try:
        token_obj = await resolve_google_meet_access_token(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            access_token=access_token,
            expires_at=int(expires_at) if expires_at is not None else None,
        )
        checks.append(
            OAuthDoctorCheck(
                id="oauth-token",
                ok=True,
                message=(
                    "Refresh token minted an access token"
                    if token_obj.refreshed
                    else "Cached access token is still valid"
                ),
            )
        )
    except Exception as err:
        checks.append(
            OAuthDoctorCheck(
                id="oauth-token",
                ok=False,
                message=sanitize_oauth_error_message(err),
            )
        )
        return OAuthDoctorReport(ok=False, configured=True, checks=checks)

    meeting_uri: str | None = None
    created_space_name: str | None = None

    meeting = options.get("meeting")
    if meeting and str(meeting).strip() and token_obj:
        try:
            space = await fetch_google_meet_space(
                access_token=token_obj.access_token,
                meeting=str(meeting).strip(),
            )
            checks.append(
                OAuthDoctorCheck(
                    id="meet-spaces-get",
                    ok=True,
                    message=f"Resolved {space.name}",
                )
            )
            meeting_uri = space.meeting_uri
        except Exception as err:
            checks.append(
                OAuthDoctorCheck(
                    id="meet-spaces-get",
                    ok=False,
                    message=sanitize_oauth_error_message(err),
                )
            )

    if options.get("createSpace") and token_obj:
        try:
            created = await create_google_meet_space(access_token=token_obj.access_token)
            checks.append(
                OAuthDoctorCheck(
                    id="meet-spaces-create",
                    ok=True,
                    message=f"Created {created.space.name}",
                )
            )
            created_space_name = created.space.name
            meeting_uri = created.meeting_uri
        except Exception as err:
            checks.append(
                OAuthDoctorCheck(
                    id="meet-spaces-create",
                    ok=False,
                    message=sanitize_oauth_error_message(err),
                )
            )

    all_ok = all(c.ok for c in checks)
    return OAuthDoctorReport(
        ok=all_ok,
        configured=True,
        token_source="refresh-token" if token_obj.refreshed else "cached-access-token",
        expires_at=token_obj.expires_at,
        meeting_uri=meeting_uri,
        created_space=created_space_name,
        checks=checks,
    )


def write_oauth_doctor_report(report: OAuthDoctorReport) -> None:
    write_stdout_line("Google Meet OAuth: %s", "OK" if report.ok else "needs attention")
    write_stdout_line("configured: %s", "yes" if report.configured else "no")
    if report.token_source:
        write_stdout_line("token source: %s", report.token_source)
    if report.meeting_uri:
        write_stdout_line("meeting uri: %s", report.meeting_uri)
    for check in report.checks:
        write_stdout_line("[%s] %s: %s", "ok" if check.ok else "fail", check.id, check.message)


def register_google_meet_doctor_command(context: GoogleMeetCliCommandContext) -> None:
    doctor_parser = context.subparsers.add_parser(
        "doctor", help="Show human-readable Meet session/browser/realtime health"
    )
    doctor_parser.add_argument("session_id", nargs="?", help="Meet session ID")
    doctor_parser.add_argument(
        "--oauth",
        action="store_true",
        help="Verify Google Meet OAuth token refresh without printing secrets",
    )
    doctor_parser.add_argument(
        "--meeting", help="Also verify spaces.get for a Meet URL, code, or spaces/{id}"
    )
    doctor_parser.add_argument(
        "--create-space",
        action="store_true",
        dest="createSpace",
        help="Also verify spaces.create by creating a throwaway Meet space",
    )
    doctor_parser.add_argument("--access-token", dest="accessToken", help="Access token override")
    doctor_parser.add_argument(
        "--refresh-token", dest="refreshToken", help="Refresh token override"
    )
    doctor_parser.add_argument("--client-id", dest="clientId", help="OAuth client id override")
    doctor_parser.add_argument(
        "--client-secret", dest="clientSecret", help="OAuth client secret override"
    )
    doctor_parser.add_argument(
        "--expires-at",
        dest="expiresAt",
        help="Cached access token expiry as unix epoch milliseconds",
    )
    doctor_parser.add_argument("--json", action="store_true", help="Print JSON output")

    async def handle_doctor(args: Any) -> None:
        opts = vars(args)
        if opts.get("oauth"):
            report = await build_oauth_doctor_report(context.config, opts)
            if opts.get("json"):
                write_stdout_json(report)
            else:
                write_oauth_doctor_report(report)
            return

        session_id = opts.get("session_id")
        delegated = await call_google_meet_gateway(
            {
                "callGateway": context.call_gateway,
                "method": "googlemeet.status",
                "payload": {"sessionId": session_id},
            }
        )
        if delegated.get("ok"):
            status = delegated["payload"]
            if opts.get("json"):
                write_stdout_json(status)
            else:
                write_doctor_status(status)
            return

        rt = await context.ensure_runtime()
        status = await rt.status(session_id)
        if opts.get("json"):
            write_stdout_json(status)
        else:
            write_doctor_status(status)

    doctor_parser.set_defaults(func=handle_doctor)


async def handle_doctor_command(args: Any, ctx: Any) -> int:
    """Handle `googlemeet doctor` CLI subcommand."""
    from .doctor import run_google_meet_doctor
    from .cli_shared import write_output

    fix = getattr(args, "fix", False)
    res = await run_google_meet_doctor(config=ctx.config, fix=fix)
    if not res.is_ok:
        write_output(ctx, {"error": str(res.error)}, is_error=True)
        return 1

    report = res.unwrap()
    write_output(ctx, report)
    return 0
