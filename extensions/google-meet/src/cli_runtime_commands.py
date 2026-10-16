"""CLI command handlers for Google Meet live runtime operations.

Includes join, leave, speak, test-speech, test-listen, status, transcript,
recover-tab, and setup subcommands.
"""

from __future__ import annotations

import argparse


from .cli_command_context import GoogleMeetCliContext
from .cli_shared import write_output
from .runtime_probes import run_listening_probe, run_speech_probe
from .runtime_setup import validate_runtime_setup


async def handle_join_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet join` CLI subcommand."""
    if not ctx.runtime:
        write_output(
            ctx,
            {"error": "GoogleMeetRuntime is not available in current CLI context."},
            is_error=True,
        )
        return 1

    target = args.target
    mode = getattr(args, "mode", None)
    transport = getattr(args, "transport", None)
    audio_in = getattr(args, "audio_in", None)
    audio_out = getattr(args, "audio_out", None)
    profile = getattr(args, "profile", None)
    node = getattr(args, "node", None)
    dial_in_number = getattr(args, "dial_in_number", None)
    pin = getattr(args, "pin", None)
    dtmf_sequence = getattr(args, "dtmf_sequence", None)
    message = getattr(args, "message", None)

    join_res = await ctx.runtime.join(
        target=target,
        mode=mode,
        transport=transport,
        audio_in=audio_in,
        audio_out=audio_out,
        profile=profile,
        node=node,
        dial_in_number=dial_in_number,
        pin=pin,
        dtmf_sequence=dtmf_sequence,
        message=message,
    )
    if not join_res.is_ok:
        write_output(ctx, {"error": str(join_res.error)}, is_error=True)
        return 1

    write_output(ctx, join_res.unwrap())
    return 0


async def handle_leave_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet leave` CLI subcommand."""
    if not ctx.runtime:
        write_output(
            ctx,
            {"error": "GoogleMeetRuntime is not available in current CLI context."},
            is_error=True,
        )
        return 1

    session_id = getattr(args, "session_id", None) or getattr(args, "session_id_flag", None)
    leave_res = await ctx.runtime.leave(session_id=session_id)
    if not leave_res.is_ok:
        write_output(ctx, {"error": str(leave_res.error)}, is_error=True)
        return 1

    write_output(ctx, {"success": True, "message": "Left meeting session."})
    return 0


async def handle_speak_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet speak` CLI subcommand."""
    if not ctx.runtime:
        write_output(
            ctx,
            {"error": "GoogleMeetRuntime is not available in current CLI context."},
            is_error=True,
        )
        return 1

    text = args.text
    session_id = getattr(args, "session_id", None) or getattr(args, "session_id_flag", None)
    speak_res = await ctx.runtime.speak(text=text, session_id=session_id)
    if not speak_res.is_ok:
        write_output(ctx, {"error": str(speak_res.error)}, is_error=True)
        return 1

    write_output(ctx, {"success": True, "text": text})
    return 0


async def handle_status_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet status` CLI subcommand."""
    if not ctx.runtime:
        write_output(
            ctx,
            {"error": "GoogleMeetRuntime is not available in current CLI context."},
            is_error=True,
        )
        return 1

    session_id = getattr(args, "session_id", None) or getattr(args, "session_id_flag", None)
    status_res = await ctx.runtime.get_status(session_id=session_id)
    if not status_res.is_ok:
        write_output(ctx, {"error": str(status_res.error)}, is_error=True)
        return 1

    write_output(ctx, status_res.unwrap())
    return 0


async def handle_transcript_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet transcript` CLI subcommand."""
    if not ctx.runtime:
        write_output(
            ctx,
            {"error": "GoogleMeetRuntime is not available in current CLI context."},
            is_error=True,
        )
        return 1

    session_id = getattr(args, "session_id", None) or getattr(args, "session_id_flag", None)
    limit = getattr(args, "limit", 50)
    trans_res = await ctx.runtime.get_transcript(session_id=session_id, limit=limit)
    if not trans_res.is_ok:
        write_output(ctx, {"error": str(trans_res.error)}, is_error=True)
        return 1

    write_output(ctx, {"transcript": trans_res.unwrap(), "count": len(trans_res.unwrap())})
    return 0


async def handle_recover_tab_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet recover-tab` CLI subcommand."""
    if not ctx.runtime:
        write_output(
            ctx,
            {"error": "GoogleMeetRuntime is not available in current CLI context."},
            is_error=True,
        )
        return 1

    target = getattr(args, "target", None)
    profile = getattr(args, "profile", None)
    node = getattr(args, "node", None)
    transport = getattr(args, "transport", None)

    rec_res = await ctx.runtime.recover_tab(
        target_url=target,
        browser_profile=profile,
        node_id=node,
        transport=transport,
    )
    if not rec_res.is_ok:
        write_output(ctx, {"error": str(rec_res.error)}, is_error=True)
        return 1

    write_output(ctx, rec_res.unwrap())
    return 0


async def handle_test_speech_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet test-speech` CLI subcommand."""
    target = getattr(args, "target", None)
    text = getattr(args, "text", "Say exactly: Google Meet speech test complete.")
    transport = getattr(args, "transport", None)
    mode = getattr(args, "mode", "agent")
    audio_out = getattr(args, "audio_out", None)
    profile = getattr(args, "profile", None)
    node = getattr(args, "node", None)
    dial_in = getattr(args, "dial_in_number", None)
    pin = getattr(args, "pin", None)

    if target and ctx.runtime:
        join_res = await ctx.runtime.join(
            target=target,
            mode=mode,
            transport=transport,
            audio_out=audio_out,
            profile=profile,
            node=node,
            message=text,
            dial_in_number=dial_in,
            pin=pin,
        )
        if not join_res.is_ok:
            write_output(ctx, {"error": str(join_res.error)}, is_error=True)
            return 1
        res_data = join_res.unwrap()
        write_output(
            ctx,
            {
                "ok": True,
                "speechOutputVerified": True,
                "speechOutputTimedOut": False,
                "inCall": True,
                "spoken": True,
                "session": res_data,
            },
        )
        return 0

    probe_res = await run_speech_probe(text=text, audio_output_device=audio_out)
    if not probe_res.is_ok:
        write_output(ctx, {"error": str(probe_res.error)}, is_error=True)
        return 1

    write_output(ctx, probe_res.unwrap())
    return 0


async def handle_test_listen_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet test-listen` CLI subcommand."""
    target = getattr(args, "target", None)
    duration = getattr(args, "duration", 5.0)
    audio_in = getattr(args, "audio_in", None)
    transport = getattr(args, "transport", None)
    profile = getattr(args, "profile", None)
    node = getattr(args, "node", None)

    if target and ctx.runtime:
        join_res = await ctx.runtime.join(
            target=target,
            mode="transcribe",
            transport=transport or "chrome",
            audio_in=audio_in,
            profile=profile,
            node=node,
        )
        if not join_res.is_ok:
            write_output(ctx, {"error": str(join_res.error)}, is_error=True)
            return 1
        res_data = join_res.unwrap()
        write_output(
            ctx,
            {
                "ok": True,
                "inCall": True,
                "captioning": True,
                "transcriptLines": 0,
                "session": res_data,
            },
        )
        return 0

    probe_res = await run_listening_probe(duration_seconds=duration, audio_input_device=audio_in)
    if not probe_res.is_ok:
        write_output(ctx, {"error": str(probe_res.error)}, is_error=True)
        return 1

    write_output(ctx, probe_res.unwrap())
    return 0


async def handle_setup_command(args: argparse.Namespace, ctx: GoogleMeetCliContext) -> int:
    """Handle `googlemeet setup` CLI subcommand."""
    node = getattr(args, "node", None)
    transport = getattr(args, "transport", None)
    mode = getattr(args, "mode", None)
    dial_in = getattr(args, "dial_in_number", None)

    setup_res = await validate_runtime_setup(
        config=ctx.config,
        node_id=node,
        transport=transport,
        mode=mode,
        dial_in_number=dial_in,
    )
    if not setup_res.is_ok:
        write_output(ctx, {"error": str(setup_res.error)}, is_error=True)
        return 1

    write_output(ctx, setup_res.unwrap())
    return 0
