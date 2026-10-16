"""Helper routines and unified action dispatcher for Voice Call."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from .config import VoiceCallConfig, resolve_voice_call_config
from .doctor import run_voice_call_doctor
from .runtime import VoiceCallRuntime
from .setup import get_voice_call_setup_status

# Process-bounded registry for async continue operations (voicecall.continue.start / result)
_ASYNC_OPERATIONS: dict[str, dict[str, Any]] = {}


async def execute_voice_call_action(
    *,
    action_name: str,
    params: dict[str, Any],
    raw_config: dict[str, Any],
    runtime: VoiceCallRuntime | None = None,
) -> dict[str, Any]:
    """Unified dispatcher for all voice_call tool actions and voicecall.* RPC methods."""
    rt = runtime
    if not rt:
        cfg_res = resolve_voice_call_config(raw_config)
        cfg = cfg_res.unwrap() if cfg_res.is_ok else VoiceCallConfig()
        rt = VoiceCallRuntime(cfg)

    action = action_name.lower().replace(".", "_").replace("-", "_")

    if action in (
        "call",
        "initiate",
        "initiate_call",
        "start",
        "voicecall_initiate",
        "voicecall_start",
    ):
        to_num = (
            params.get("to")
            or params.get("to_number")
            or params.get("toNumber")
            or rt.config.to_number
            or ""
        )
        from_num = params.get("from") or params.get("from_number") or params.get("fromNumber")
        message = params.get("message") or params.get("text")
        mode = params.get("mode") or rt.config.mode or "turn"
        agent_id = params.get("agent") or params.get("agent_id") or params.get("agentId")
        dtmf_seq = params.get("dtmfSequence") or params.get("dtmf_sequence")
        session_key = params.get("sessionKey") or params.get("session_key")
        metadata = dict(params.get("metadata") or {})
        if session_key:
            metadata["session_key"] = session_key

        # Validate dtmfSequence constraint: only valid with mode: "conversation"
        if dtmf_seq:
            if mode not in ("conversation", "turn"):
                return {
                    "ok": False,
                    "error": f"dtmfSequence is only valid with mode: 'conversation' (got '{mode}')",
                }
            metadata["pre_connect_dtmf"] = dtmf_seq

        res = await rt.initiate(
            to_number=to_num,
            from_number=from_num,
            message=message,
            mode=mode,
            agent_id=agent_id,
            metadata=metadata,
        )
        if not res.is_ok:
            return {"ok": False, "error": res.unwrap_err()}

        val = res.unwrap()
        return {
            "ok": val.ok,
            "callId": val.call_id,
            "providerCallId": val.provider_call_id,
            "status": val.status,
        }

    elif action in ("voicecall_continue_start",):
        call_id = (
            params.get("callId")
            or params.get("call_id")
            or params.get("sessionId")
            or params.get("session_id")
        )
        message = params.get("message") or params.get("text") or ""
        op_id = f"op_{uuid.uuid4().hex[:10]}"

        async def _run_async_continue() -> None:
            _ASYNC_OPERATIONS[op_id] = {"status": "running"}
            res = await rt.speak(text=message, session_id=call_id)
            if res.is_ok:
                _ASYNC_OPERATIONS[op_id] = {
                    "status": "completed",
                    "ok": True,
                    "text": res.unwrap().text,
                }
            else:
                _ASYNC_OPERATIONS[op_id] = {
                    "status": "failed",
                    "ok": False,
                    "error": res.unwrap_err(),
                }

        asyncio.create_task(_run_async_continue())
        return {"ok": True, "operationId": op_id, "status": "running"}

    elif action in ("voicecall_continue_result",):
        op_id = params.get("operationId") or params.get("operation_id") or ""
        op = _ASYNC_OPERATIONS.get(op_id)
        if not op:
            return {"ok": False, "error": f"Operation not found: {op_id}"}
        return dict(op)

    elif action in (
        "continue",
        "continue_call",
        "voicecall_continue",
    ):
        call_id = (
            params.get("callId")
            or params.get("call_id")
            or params.get("sessionId")
            or params.get("session_id")
        )
        message = params.get("message") or params.get("text") or ""
        res = await rt.speak(text=message, session_id=call_id)
        if not res.is_ok:
            return {"ok": False, "error": res.unwrap_err()}
        val = res.unwrap()
        session = rt.find_session(session_id=call_id)
        transcript = [
            {"speaker": t.speaker, "text": t.text, "timestamp": t.timestamp}
            for t in (session.transcript if session else [])
        ]
        return {"ok": val.ok, "text": val.text, "transcript": transcript}

    elif action in ("speak", "speak_to_user", "voicecall_speak"):
        call_id = (
            params.get("callId")
            or params.get("call_id")
            or params.get("sessionId")
            or params.get("session_id")
        )
        text = params.get("text") or params.get("message") or ""
        res = await rt.speak(text=text, session_id=call_id)
        if not res.is_ok:
            return {"ok": False, "error": res.unwrap_err()}
        val = res.unwrap()
        return {"ok": val.ok, "text": val.text}

    elif action in ("dtmf", "send_dtmf", "voicecall_dtmf"):
        call_id = (
            params.get("callId")
            or params.get("call_id")
            or params.get("sessionId")
            or params.get("session_id")
        )
        digits = str(params.get("digits") or params.get("tones") or "")
        res = await rt.send_dtmf(digits=digits, session_id=call_id)
        if not res.is_ok:
            return {"ok": False, "error": res.unwrap_err()}
        val = res.unwrap()
        return {"ok": val.ok, "digits": val.digits}

    elif action in ("end", "end_call", "hangup", "voicecall_end"):
        call_id = (
            params.get("callId")
            or params.get("call_id")
            or params.get("sessionId")
            or params.get("session_id")
        )
        res = await rt.end_call(session_id=call_id)
        return {"ok": res.is_ok if hasattr(res, "is_ok") else True}

    elif action in ("status", "get_status", "voicecall_status"):
        call_id = (
            params.get("callId")
            or params.get("call_id")
            or params.get("sessionId")
            or params.get("session_id")
        )
        phone = params.get("phone") or params.get("phoneNumber") or params.get("phone_number")
        if not call_id and not phone:
            # List all active calls
            active_list = [
                {
                    "id": s.id,
                    "status": s.status,
                    "direction": s.direction,
                    "provider": s.provider,
                    "to": s.to_number,
                    "from": s.from_number,
                    "durationSeconds": s.duration_seconds,
                    "agentId": s.agent_id,
                }
                for s in rt._sessions.values()
                if s.is_active
            ]
            return {"ok": True, "activeCalls": active_list, "count": len(active_list)}

        res = await rt.get_status(session_id=call_id, phone_number=phone)
        return res.unwrap() if res.is_ok else {"active": False, "session": None}

    elif action in ("smoke", "smoke_test", "voicecall_smoke"):
        to_num = params.get("to") or params.get("to_number") or params.get("toNumber")
        is_live = bool(params.get("live", params.get("yes", False)))
        res = await rt.smoke_test(to_number=to_num, live=is_live)
        return res.unwrap() if res.is_ok else {"ok": False, "error": res.unwrap_err()}

    elif action in ("setup", "setup_status", "voicecall_setup"):
        cfg_res = resolve_voice_call_config(raw_config)
        cfg = cfg_res.unwrap() if cfg_res.is_ok else VoiceCallConfig()
        status = get_voice_call_setup_status(cfg)
        return {
            "ok": status.ok,
            "checks": [{"id": c.id, "ok": c.ok, "message": c.message} for c in status.checks],
        }

    elif action in ("doctor", "voicecall_doctor"):
        fix = bool(params.get("fix", False))
        res = await run_voice_call_doctor(config=raw_config, fix=fix)
        return res.unwrap() if res.is_ok else {"ok": False, "error": res.unwrap_err()}

    return {"ok": False, "error": f"Unknown Voice Call action: {action_name}"}
