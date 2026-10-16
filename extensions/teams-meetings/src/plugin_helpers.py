"""Helper routines and action dispatcher for Teams Meetings."""

from __future__ import annotations

from typing import Any


async def execute_teams_meetings_action(
    *,
    action_name: str,
    params: dict[str, Any],
    raw_config: dict[str, Any],
    runtime: Any = None,
) -> dict[str, Any]:
    """Unified dispatcher for all teams_meetings tool actions."""
    action = action_name.lower().replace("_", "-")

    if action == "status":
        if runtime:
            status_res = await runtime.get_status(
                session_id=params.get("sessionId") or params.get("session_id")
            )
            return (
                status_res.unwrap()
                if hasattr(status_res, "unwrap")
                else {"active": False, "session": None}
            )
        return {"active": False, "session": None}

    elif action == "join":
        if not runtime:
            return {"ok": False, "error": "TeamsMeetingsRuntime unavailable"}
        target = params.get("url") or params.get("target") or ""
        join_res = await runtime.join(
            target=target,
            mode=params.get("mode"),
            transport=params.get("transport"),
            audio_in=params.get("audioIn") or params.get("audio_in"),
            audio_out=params.get("audioOut") or params.get("audio_out"),
            profile=params.get("profile") or params.get("browserProfile"),
            node=params.get("node") or params.get("nodeId"),
            message=params.get("message") or params.get("text"),
        )
        return (
            join_res.unwrap()
            if hasattr(join_res, "unwrap")
            else {"ok": False, "error": str(join_res)}
        )

    elif action == "leave":
        if not runtime:
            return {"ok": False, "error": "TeamsMeetingsRuntime unavailable"}
        leave_res = await runtime.leave(
            session_id=params.get("sessionId") or params.get("session_id")
        )
        return {"ok": leave_res.is_ok if hasattr(leave_res, "is_ok") else True}

    elif action == "speak":
        if not runtime:
            return {"ok": False, "error": "TeamsMeetingsRuntime unavailable"}
        text = params.get("text") or params.get("message") or ""
        speak_res = await runtime.speak(
            text=text, session_id=params.get("sessionId") or params.get("session_id")
        )
        return {"ok": speak_res.is_ok if hasattr(speak_res, "is_ok") else True, "text": text}

    elif action == "transcript":
        if not runtime:
            return {"transcript": [], "count": 0}
        trans_res = await runtime.get_transcript(
            session_id=params.get("sessionId") or params.get("session_id"),
            limit=params.get("limit") or 50,
        )
        lines = trans_res.unwrap() if hasattr(trans_res, "unwrap") else []
        return {"transcript": lines, "count": len(lines)}

    elif action in ("recover-current-tab", "recover_current_tab", "recover-tab", "recover_tab"):
        if runtime:
            rec_res = await runtime.recover_tab(params)
            return (
                rec_res.unwrap()
                if hasattr(rec_res, "unwrap")
                else (rec_res if isinstance(rec_res, dict) else {"found": False})
            )
        return {"found": False, "error": "TeamsMeetingsRuntime unavailable"}

    elif action == "doctor":
        from .doctor import run_teams_meetings_doctor

        doc_res = await run_teams_meetings_doctor(config=raw_config, fix=params.get("fix", False))
        return doc_res.unwrap() if hasattr(doc_res, "unwrap") else {}

    elif action in ("setup", "setup_status"):
        from .runtime_setup import validate_teams_meetings_runtime_setup

        setup_res = await validate_teams_meetings_runtime_setup(
            config=raw_config,
            node_id=params.get("node"),
            transport=params.get("transport"),
            mode=params.get("mode"),
        )
        return setup_res.unwrap() if hasattr(setup_res, "unwrap") else {}

    elif action in ("test-speech", "test_speech"):
        from .runtime_probes import run_speech_probe

        probe_res = await run_speech_probe(
            text=params.get("text", "Microsoft Teams audio speech probe test."),
            audio_output_device=params.get("audioOut"),
        )
        return probe_res.unwrap() if hasattr(probe_res, "unwrap") else {}

    elif action in ("test-listen", "test_listen"):
        from .runtime_probes import run_listening_probe

        probe_res = await run_listening_probe(
            duration_seconds=params.get("duration", 5.0),
            audio_input_device=params.get("audioIn"),
        )
        return probe_res.unwrap() if hasattr(probe_res, "unwrap") else {}

    return {"ok": False, "error": f"Unknown action: {action_name}"}
