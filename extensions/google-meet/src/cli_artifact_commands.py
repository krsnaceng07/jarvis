"""CLI command handlers for Google Meet artifacts, attendance, and export bundles."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .cli_command_context import GoogleMeetCliContext
from .cli_export import (
    format_attendance_csv,
    format_attendance_markdown,
    generate_export_bundle,
    write_export_bundle_to_disk,
)
from .cli_shared import write_output
from .config import resolve_google_meet_config
from .meet import fetch_google_meet_artifacts, get_google_meet_attendance
from .meet_api import get_active_google_meet_conference, get_latest_google_meet_conference_for_space
from .meet_url import parse_google_meet_target


async def _resolve_conference_record_name(
    target: str,
    cfg: Any,
) -> str | None:
    """Resolve conferenceRecord name from string target or Meet URL/space."""
    if target.startswith("conferenceRecords/"):
        return target

    parsed = parse_google_meet_target(target)
    space_name = parsed.space_name or target
    if not space_name.startswith("spaces/"):
        space_name = f"spaces/{space_name}"

    # Try active conference first, then latest completed conference
    active_res = await get_active_google_meet_conference(config=cfg, space_name=space_name)
    if active_res.is_ok and active_res.unwrap():
        return active_res.unwrap().name

    latest_res = await get_latest_google_meet_conference_for_space(
        config=cfg, space_name=space_name
    )
    if latest_res.is_ok and latest_res.unwrap():
        return latest_res.unwrap().name

    return None


async def handle_artifacts_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet artifacts` CLI subcommand."""
    config_res = resolve_google_meet_config(ctx.config)
    if not config_res.is_ok:
        write_output(ctx, {"error": str(config_res.error)}, is_error=True)
        return 1
    cfg = config_res.unwrap()

    target = args.target
    conf_name = await _resolve_conference_record_name(target, cfg)
    if not conf_name:
        write_output(
            ctx,
            {"error": f"Could not find any conference record for target '{target}'."},
            is_error=True,
        )
        return 1

    art_res = await fetch_google_meet_artifacts(
        config=cfg,
        conference_record_name=conf_name,
    )
    if not art_res.is_ok:
        write_output(ctx, {"error": str(art_res.error)}, is_error=True)
        return 1

    write_output(ctx, art_res.unwrap())
    return 0


async def handle_attendance_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet attendance` CLI subcommand."""
    config_res = resolve_google_meet_config(ctx.config)
    if not config_res.is_ok:
        write_output(ctx, {"error": str(config_res.error)}, is_error=True)
        return 1
    cfg = config_res.unwrap()

    target = args.target
    conf_name = await _resolve_conference_record_name(target, cfg)
    if not conf_name:
        write_output(
            ctx,
            {"error": f"Could not find any conference record for target '{target}'."},
            is_error=True,
        )
        return 1

    late_threshold = getattr(args, "late_threshold_seconds", 300)
    early_threshold = getattr(args, "early_leave_threshold_seconds", 300)

    att_res = await get_google_meet_attendance(
        config=cfg,
        conference_record_name=conf_name,
        late_threshold_seconds=late_threshold,
        early_leave_threshold_seconds=early_threshold,
    )
    if not att_res.is_ok:
        write_output(ctx, {"error": str(att_res.error)}, is_error=True)
        return 1

    attendance_data = att_res.unwrap()
    fmt = getattr(args, "format", "json")
    if fmt == "csv":
        print(format_attendance_csv(attendance_data))
    elif fmt in ("md", "markdown"):
        print(format_attendance_markdown(attendance_data))
    else:
        write_output(ctx, attendance_data)

    return 0


async def handle_export_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet export` CLI subcommand."""
    config_res = resolve_google_meet_config(ctx.config)
    if not config_res.is_ok:
        write_output(ctx, {"error": str(config_res.error)}, is_error=True)
        return 1
    cfg = config_res.unwrap()

    target = args.target
    conf_name = await _resolve_conference_record_name(target, cfg)
    if not conf_name:
        write_output(
            ctx,
            {"error": f"Could not find any conference record for target '{target}'."},
            is_error=True,
        )
        return 1

    include_drive = not getattr(args, "no_drive", False)
    bundle_res = await generate_export_bundle(
        config=cfg,
        conference_record_name=conf_name,
        include_drive_content=include_drive,
    )
    if not bundle_res.is_ok:
        write_output(ctx, {"error": str(bundle_res.error)}, is_error=True)
        return 1

    bundle_data = bundle_res.unwrap()
    output_target = getattr(args, "output", None)
    bundle_format = getattr(args, "format", "zip")

    if not output_target:
        # Default filename based on conference record ID
        record_id = conf_name.replace("conferenceRecords/", "")
        output_target = (
            f"google-meet-export-{record_id}.zip"
            if bundle_format == "zip"
            else f"google-meet-export-{record_id}"
        )

    out_path = Path(output_target)
    written_path = write_export_bundle_to_disk(
        bundle_files=bundle_data["files"],
        output_path=out_path,
        as_zip=(bundle_format == "zip"),
    )

    result_payload = {
        "success": True,
        "conferenceRecord": conf_name,
        "format": bundle_format,
        "outputPath": str(written_path),
        "filesIncluded": list(bundle_data["files"].keys()),
    }
    write_output(ctx, result_payload)
    return 0
