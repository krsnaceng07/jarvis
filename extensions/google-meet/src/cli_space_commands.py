"""CLI command handlers for Google Meet spaces, conference lifecycle, and Calendar."""

from __future__ import annotations

import argparse


from .calendar import list_upcoming_calendar_events_with_meet
from .cli_command_context import GoogleMeetCliContext
from .cli_shared import write_output
from .config import resolve_google_meet_config
from .create import create_google_meet_space
from .meet import get_google_meet_preflight_report
from .meet_api import end_active_google_meet_conference, get_google_meet_space
from .meet_url import parse_google_meet_target


async def handle_create_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet create` CLI subcommand."""
    config_res = resolve_google_meet_config(ctx.config)
    if not config_res.is_ok:
        write_output(ctx, {"error": str(config_res.error)}, is_error=True)
        return 1
    cfg = config_res.unwrap()

    access_type = getattr(args, "access_type", None)
    profile = getattr(args, "profile", None)
    node = getattr(args, "node", None)

    create_res = await create_google_meet_space(
        config=cfg,
        access_type=access_type,
        browser_profile=profile,
        node_id=node,
    )
    if not create_res.is_ok:
        err = create_res.error
        write_output(ctx, {"error": str(err)}, is_error=True)
        return 1

    space_data = create_res.unwrap()

    # If --join was requested, start runtime join session
    should_join = getattr(args, "join", False)
    if should_join and ctx.runtime:
        join_res = await ctx.runtime.join(
            target=space_data["meetingUri"],
            mode=getattr(args, "mode", None),
            transport=getattr(args, "transport", None),
            audio_in=getattr(args, "audio_in", None),
            audio_out=getattr(args, "audio_out", None),
            profile=profile,
            node=node,
        )
        if not join_res.is_ok:
            space_data["joinError"] = str(join_res.error)
        else:
            space_data["session"] = join_res.unwrap()

    write_output(ctx, space_data)
    return 0


async def handle_end_active_conference_command(
    args: argparse.Namespace, ctx: GoogleMeetCliContext
) -> int:
    """Handle `googlemeet end-active-conference` CLI subcommand."""
    config_res = resolve_google_meet_config(ctx.config)
    if not config_res.is_ok:
        write_output(ctx, {"error": str(config_res.error)}, is_error=True)
        return 1
    cfg = config_res.unwrap()

    target = args.target
    parsed = parse_google_meet_target(target)
    space_name = parsed.space_name or target
    if not space_name.startswith("spaces/"):
        space_name = f"spaces/{space_name}"

    end_res = await end_active_google_meet_conference(config=cfg, space_name=space_name)
    if not end_res.is_ok:
        write_output(ctx, {"error": str(end_res.error)}, is_error=True)
        return 1

    write_output(ctx, {"success": True, "space": space_name, "message": "Active conference ended."})
    return 0


async def handle_resolve_space_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet resolve-space` CLI subcommand."""
    config_res = resolve_google_meet_config(ctx.config)
    if not config_res.is_ok:
        write_output(ctx, {"error": str(config_res.error)}, is_error=True)
        return 1
    cfg = config_res.unwrap()

    target = args.target
    parsed = parse_google_meet_target(target)
    space_name = parsed.space_name or target
    if not space_name.startswith("spaces/"):
        space_name = f"spaces/{space_name}"

    space_res = await get_google_meet_space(config=cfg, space_name=space_name)
    if not space_res.is_ok:
        write_output(ctx, {"error": str(space_res.error)}, is_error=True)
        return 1

    write_output(ctx, space_res.unwrap().to_dict())
    return 0


async def handle_preflight_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet preflight` CLI subcommand."""
    config_res = resolve_google_meet_config(ctx.config)
    if not config_res.is_ok:
        write_output(ctx, {"error": str(config_res.error)}, is_error=True)
        return 1
    cfg = config_res.unwrap()

    target = getattr(args, "target", None)
    parsed = parse_google_meet_target(target) if target else None
    space_name = parsed.space_name if parsed else None
    if space_name and not space_name.startswith("spaces/"):
        space_name = f"spaces/{space_name}"

    report_res = await get_google_meet_preflight_report(
        config=cfg,
        space_name=space_name,
    )
    if not report_res.is_ok:
        write_output(ctx, {"error": str(report_res.error)}, is_error=True)
        return 1

    write_output(ctx, report_res.unwrap())
    return 0


async def handle_calendar_events_command(
    args: argparse.Namespace, ctx: GoogleMeetCliContext
) -> int:
    """Handle `googlemeet calendar-events` CLI subcommand."""
    config_res = resolve_google_meet_config(ctx.config)
    if not config_res.is_ok:
        write_output(ctx, {"error": str(config_res.error)}, is_error=True)
        return 1
    cfg = config_res.unwrap()

    if not cfg.oauth or not cfg.oauth.access_token:
        write_output(
            ctx, {"error": "OAuth access token required for Calendar operations."}, is_error=True
        )
        return 1

    limit = getattr(args, "limit", 10) or 10
    time_min = getattr(args, "time_min", None)
    time_max = getattr(args, "time_max", None)

    events_res = await list_upcoming_calendar_events_with_meet(
        token=cfg.oauth.access_token,
        limit=limit,
        time_min=time_min,
        time_max=time_max,
    )
    if not events_res.is_ok:
        write_output(ctx, {"error": str(events_res.error)}, is_error=True)
        return 1

    write_output(ctx, {"events": events_res.unwrap(), "count": len(events_res.unwrap())})
    return 0
