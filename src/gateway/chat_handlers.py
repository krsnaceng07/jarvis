"""Gateway chat RPC handlers — mirrors OpenClaw's src/gateway/server-methods/chat*.ts.

Handles:
- chat.send: accept message, session_id/key, model override → execute agent turn.
- chat.abort: abort active turn for a session.
- chat.history: return message history for a session (read from SQLite agent_db).
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from src.sessions.session_store import SessionStore, get_default_session_store
from .agent_runs import AgentRunService

_log = logging.getLogger("jarvis.gateway.chat")


def _default_agent_runner(
    params: dict[str, Any],
    abort: Any,
    emit: Any,
) -> dict[str, Any]:
    """Fallback agent turn executor when no custom runner is wired."""
    emit({"stream": "lifecycle", "phase": "start"})
    if hasattr(abort, "is_set") and abort.is_set():
        return {"status": "aborted"}

    # Attempt to use packages/agent_runtime if available
    try:
        import jarvis_agent  # noqa: F401

        # Minimal turn acknowledgment
        emit({"stream": "lifecycle", "phase": "executing"})
    except ImportError:
        pass

    emit({"stream": "lifecycle", "phase": "end"})
    return {
        "status": "completed",
        "output": f"Acknowledged: {params.get('message', '')[:100]}",
    }


def make_chat_handlers(
    agent_runs: AgentRunService | None = None,
    session_store: SessionStore | None = None,
) -> dict[str, Any]:
    """Build and return gateway RPC handlers for chat operations."""
    active_agent_runs = agent_runs or AgentRunService(_default_agent_runner)
    store = session_store or get_default_session_store()

    def send_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        message = params.get("message")
        if not isinstance(message, str) or not message.strip():
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(
                -32602, "Invalid params: 'message' is required and must be a non-empty string"
            )

        session_key = str(
            params.get("sessionKey")
            or params.get("sessionId")
            or params.get("session_id")
            or "default"
        )
        agent_id = str(params.get("agentId") or params.get("agent_id") or "local")
        model = params.get("model") or params.get("model_ref")

        # 1. Ensure session exists in the canonical store
        store.get_or_create(session_key=session_key, agent_id=agent_id, kind="direct")
        if model:
            store.set_route_pin(session_key, model_ref=str(model))

        now_ms = int(time.time() * 1000)
        msg_id = str(uuid.uuid4())

        # 2. Append user turn to store
        store.append_entry(
            session_key,
            {
                "id": msg_id,
                "kind": "user_message",
                "payload": {
                    "id": msg_id,
                    "text": message,
                    "role": "user",
                    "content": message,
                    "timestamp": now_ms,
                },
            },
        )

        # 3. Write to SQLite agent_db if available
        try:
            from jarvis_state_core.agent_db import (
                append_agent_session_entry,
                ensure_agent_session,
                open_agent_database,
            )

            db_handle = open_agent_database({"agent_id": agent_id})
            ensure_agent_session(db_handle, session_key, cwd=".", timestamp=str(now_ms))
            append_agent_session_entry(
                db_handle,
                session_key,
                {
                    "id": msg_id,
                    "role": "user",
                    "content": message,
                    "timestamp": now_ms,
                },
                timestamp=str(now_ms),
            )
        except Exception as exc:
            _log.debug("chat_handlers: optional agent_db write skipped: %s", exc)

        # 4. Dispatch agent turn
        run_params = dict(params)
        run_params["sessionKey"] = session_key
        run_params["message"] = message
        run_params["agentId"] = agent_id
        if model:
            run_params["model"] = str(model)

        run_info = active_agent_runs.agent(run_params)
        run_id = run_info.get("runId", str(uuid.uuid4()))

        return {
            "ok": True,
            "runId": run_id,
            "status": "started",
            "sessionKey": session_key,
            "acceptedAt": run_info.get("acceptedAt", now_ms),
        }

    def abort_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        run_id = params.get("runId") or params.get("run_id")
        session_key = (
            params.get("sessionKey") or params.get("sessionId") or params.get("session_id")
        )

        aborted_run_ids: list[str] = []

        if run_id:
            try:
                res = active_agent_runs.abort({"runId": str(run_id)})
                if res.get("aborted"):
                    aborted_run_ids.append(str(run_id))
            except Exception as exc:
                _log.debug("chat_handlers: abort run %s failed: %s", run_id, exc)

        if session_key and not run_id:
            target_key = str(session_key)
            with active_agent_runs._lock:
                for rid, run in active_agent_runs._runs.items():
                    if run.session_key == target_key and not run.done.is_set():
                        run.abort.set()
                        active_agent_runs._emit(run, "abort_requested")
                        aborted_run_ids.append(rid)

        return {
            "ok": True,
            "aborted": len(aborted_run_ids) > 0,
            "runIds": aborted_run_ids,
        }

    def history_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        session_key = str(
            params.get("sessionKey")
            or params.get("sessionId")
            or params.get("session_id")
            or params.get("target")
            or ""
        )
        if not session_key:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(
                -32602, "Invalid params: 'sessionKey' or 'sessionId' is required"
            )

        agent_id = str(params.get("agentId") or params.get("agent_id") or "local")
        limit = int(params.get("limit", 100))
        offset = int(params.get("offset", 0))

        messages: list[dict[str, Any]] = []

        # 1. Read from SQLite agent_db
        try:
            from jarvis_state_core.agent_db import (
                load_agent_session_entries,
                open_agent_database,
            )

            db_handle = open_agent_database({"agent_id": agent_id})
            entries = load_agent_session_entries(db_handle, session_key)
            for entry in entries:
                role = entry.get("role") or (
                    "user" if entry.get("kind") == "user_message" else "assistant"
                )
                content = (
                    entry.get("content")
                    or entry.get("text")
                    or entry.get("payload", {}).get("text", "")
                )
                messages.append(
                    {
                        "id": str(entry.get("id") or ""),
                        "role": role,
                        "content": content,
                        "timestamp": entry.get("timestamp", entry.get("created_at", "")),
                    }
                )
        except Exception as exc:
            _log.debug("chat_handlers: SQLite agent_db read skipped: %s", exc)

        # 2. Fall back to or augment from canonical session store
        if not messages:
            rec = store.get(session_key)
            if rec:
                for entry in rec.entries:
                    kind = entry.get("kind", "")
                    payload = entry.get("payload", {})
                    if kind in ("user_message", "assistant_message", "message"):
                        role = payload.get("role") or (
                            "user" if kind == "user_message" else "assistant"
                        )
                        content = payload.get("content") or payload.get("text", "")
                        messages.append(
                            {
                                "id": str(entry.get("id") or payload.get("id") or ""),
                                "role": role,
                                "content": content,
                                "timestamp": payload.get("timestamp", rec.updated_at),
                            }
                        )

        sliced = messages[offset : offset + limit] if limit else messages[offset:]

        return {
            "sessionKey": session_key,
            "sessionId": session_key,
            "messages": sliced,
            "total": len(messages),
        }

    return {
        "chat.send": send_handler,
        "chat_send": send_handler,
        "chat.abort": abort_handler,
        "chat_abort": abort_handler,
        "chat.history": history_handler,
        "chat_history": history_handler,
    }


__all__ = ["make_chat_handlers"]
