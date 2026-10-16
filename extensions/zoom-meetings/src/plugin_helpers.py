"""Unified action dispatcher for Zoom Meetings tool actions and Gateway RPCs."""

from __future__ import annotations

from typing import Any

from .config import ZoomMeetingsConfig, resolve_zoom_meetings_config
from .doctor import run_zoom_meetings_doctor
from .runtime import ZoomMeetingsRuntime
from .setup import get_zoom_meetings_setup_status


async def execute_zoom_meetings_action(
    *,
    action_name: str,
    params: dict[str, Any],
    raw_config: dict[str, Any],
    runtime: ZoomMeetingsRuntime | None = None,
) -> dict[str, Any]:
    """Unified dispatcher for all zoom_meetings tool actions and zoommeetings.* Gateway RPCs."""
    rt = runtime
    if not rt:
        cfg_res = resolve_zoom_meetings_config(raw_config)
        cfg = cfg_res.unwrap() if cfg_res.is_ok else ZoomMeetingsConfig()
        rt = ZoomMeetingsRuntime(cfg)

    action = action_name.lower().replace(".", "_").replace("-", "_")

    if action in ("join", "zoom_join", "zoommeetings_join"):
        url = params.get("url") or params.get("meetingUrl") or params.get("meeting")
        name = params.get("name") or params.get("guestName") or params.get("guest_name")
        mode = params.get("mode") or params.get("defaultMode")
        passcode = params.get("passcode") or params.get("pwd")
        meta = params.get("metadata")
        simulated_text = params.get("simulated_page_text") or params.get("simulatedPageText")

        res = await rt.join(
            url=url,
            guest_name=name,
            mode=mode,
            passcode=passcode,
            metadata=meta,
            simulated_page_text=simulated_text,
        )
        if not res.is_ok:
            return {"ok": False, "error": str(res.error)}

        val = res.unwrap()
        return {
            "ok": val.ok,
            "sessionId": val.session_id,
            "status": val.status,
            "manualAction": val.manual_action,
            "manualActionReason": val.manual_action_reason,
            "manualActionMessage": val.manual_action_message,
        }

    elif action in ("leave", "zoom_leave", "zoommeetings_leave", "end"):
        session_id = (
            params.get("sessionId")
            or params.get("session_id")
            or params.get("callId")
            or params.get("call_id")
        )
        res = await rt.leave(session_id=session_id)
        if not res.is_ok:
            return {"ok": False, "error": str(res.error)}
        return {"ok": True, "sessionId": session_id, "status": "ended"}

    elif action in ("status", "zoom_status", "zoommeetings_status"):
        session_id = (
            params.get("sessionId")
            or params.get("session_id")
            or params.get("callId")
            or params.get("call_id")
        )
        res = await rt.get_status(session_id=session_id)
        return res.unwrap() if res.is_ok else {"active": False, "session": None}

    elif action in ("transcript", "zoom_transcript", "zoommeetings_transcript"):
        session_id = (
            params.get("sessionId")
            or params.get("session_id")
            or params.get("callId")
            or params.get("call_id")
        )
        res = await rt.get_transcript(session_id=session_id)
        if not res.is_ok:
            return {"ok": False, "error": str(res.error)}
        return {"ok": True, "transcript": res.unwrap()}

    elif action in ("speak", "zoom_speak", "zoommeetings_speak"):
        session_id = (
            params.get("sessionId")
            or params.get("session_id")
            or params.get("callId")
            or params.get("call_id")
        )
        text = params.get("message") or params.get("text") or ""
        res = await rt.speak(text=text, session_id=session_id)
        if not res.is_ok:
            return {"ok": False, "error": str(res.error)}
        return res.unwrap()

    elif action in ("setup", "zoom_setup", "zoommeetings_setup"):
        cfg_res = resolve_zoom_meetings_config(raw_config)
        cfg = cfg_res.unwrap() if cfg_res.is_ok else ZoomMeetingsConfig()
        status = get_zoom_meetings_setup_status(cfg)
        return {
            "ok": status.ok,
            "checks": [{"id": c.id, "ok": c.ok, "message": c.message} for c in status.checks],
        }

    elif action in ("doctor", "zoom_doctor", "zoommeetings_doctor"):
        fix = bool(params.get("fix", False))
        res = await run_zoom_meetings_doctor(config=raw_config, fix=fix)
        return res.unwrap() if res.is_ok else {"ok": False, "error": str(res.error)}

    return {"ok": False, "error": f"Unknown Zoom Meetings action: {action_name}"}
