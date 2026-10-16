"""Teams Meetings CLI doctor command implementation."""

from __future__ import annotations

import argparse

from .cli_command_context import TeamsMeetingsCliContext
from .cli_shared import write_doctor_status, write_output
from .doctor import run_teams_meetings_doctor


async def handle_doctor_command(args: argparse.Namespace, ctx: TeamsMeetingsCliContext) -> int:
    """Handle `teamsmeetings doctor` CLI subcommand."""
    fix = getattr(args, "fix", False)
    session_id = getattr(args, "session_id", None)

    if session_id and ctx.runtime:
        status_res = await ctx.runtime.get_status(session_id=session_id)
        if status_res.is_ok:
            data = status_res.unwrap()
            if getattr(ctx, "json_mode", False):
                write_output(ctx, data)
            else:
                write_doctor_status(data.get("session"))
            return 0

    res = await run_teams_meetings_doctor(config=ctx.config, fix=fix)
    if not res.is_ok:
        write_output(ctx, {"error": str(res.error)}, is_error=True)
        return 1

    report = res.unwrap()
    write_output(ctx, report)
    return 0
