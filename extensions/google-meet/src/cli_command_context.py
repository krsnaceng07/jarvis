"""CLI command context and argument parser helpers for Google Meet subcommands."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Callable

from .config import GoogleMeetConfig
from .runtime import GoogleMeetRuntime


@dataclass
class GoogleMeetCliContext:
    config: dict[str, Any] | GoogleMeetConfig
    runtime: GoogleMeetRuntime | None = None
    json_mode: bool = False
    call_gateway: Any = None
    operation_timeout_ms: int = 30000


def add_google_meet_oauth_options(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--access-token", dest="accessToken", help="Access token override")
    parser.add_argument("--refresh-token", dest="refreshToken", help="Refresh token override")
    parser.add_argument("--client-id", dest="clientId", help="OAuth client id override")
    parser.add_argument("--client-secret", dest="clientSecret", help="OAuth client secret override")
    parser.add_argument(
        "--expires-at",
        dest="expiresAt",
        help="Cached access token expiry as unix epoch milliseconds",
    )
    return parser


def add_google_meet_meeting_option(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--meeting", dest="meeting", help="Meet URL, meeting code, or spaces/{id}")
    return parser


def add_google_meet_calendar_options(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--today", action="store_true", dest="today", help="Find a Meet link on today's calendar"
    )
    parser.add_argument(
        "--event", dest="event", help="Find a matching calendar event with a Meet link"
    )
    parser.add_argument(
        "--calendar", dest="calendar", default="primary", help="Calendar id for --today or --event"
    )
    return parser


def add_google_meet_artifact_options(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    add_google_meet_meetingOption = add_google_meet_meeting_option(parser)
    add_google_meet_meetingOption.add_argument(
        "--conference-record", dest="conferenceRecord", help="Conference record name or id"
    )
    add_google_meet_calendar_options(parser)
    add_google_meet_oauth_options(parser)
    parser.add_argument("--page-size", dest="pageSize", help="Max resources per Meet API page")
    parser.add_argument(
        "--all-conference-records",
        action="store_true",
        dest="allConferenceRecords",
        help="Fetch every conference record for --meeting",
    )
    return parser


class GoogleMeetCliCommandContext:
    def __init__(
        self,
        *,
        subparsers: Any,
        config: GoogleMeetConfig,
        ensure_runtime: Callable[[], Any],
        call_gateway: Any = None,
        operation_timeout_ms: int = 5000,
        resolve_meeting_input_fn: Callable[[GoogleMeetConfig, str | None], str],
        resolve_cli_params_fn: Callable[[dict[str, Any]], dict[str, Any]],
        resolve_cli_artifact_params_fn: Callable[[dict[str, Any]], dict[str, Any]],
        has_create_oauth_fn: Callable[[GoogleMeetConfig, dict[str, Any]], bool],
    ) -> None:
        self.subparsers = subparsers
        self.config = config
        self.ensure_runtime = ensure_runtime
        self.call_gateway = call_gateway
        self.operation_timeout_ms = operation_timeout_ms
        self.resolve_meeting_input = resolve_meeting_input_fn
        self.resolve_cli_params = resolve_cli_params_fn
        self.resolve_cli_artifact_params = resolve_cli_artifact_params_fn
        self.has_create_oauth = has_create_oauth_fn
