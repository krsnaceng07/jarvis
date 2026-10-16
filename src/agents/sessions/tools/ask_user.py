"""jarvis.agents.sessions.tools.ask_user — ask_user tool implementation.

OpenClaw parity: mirrors ``openclaw-main/src/agents/tools/ask-user-tool.ts``.

Allows the agent to ask the user up to 3 structured questions and waits for the answers.
"""
from __future__ import annotations

import time
import asyncio
import json
from typing import Any, Optional, Dict

from .tool_definition_wrapper import AgentTool


DEFAULT_ASK_USER_TIMEOUT_SECONDS = 900
MIN_ASK_USER_TIMEOUT_SECONDS = 30
MAX_ASK_USER_TIMEOUT_SECONDS = 3600
ASK_USER_RPC_GRACE_MS = 10000

# Global registry to prevent concurrent asks in the same session
_ASK_USER_QUESTIONS: Dict[str, dict] = {}


def create_ask_user_tool_definition() -> dict:
    return {
        "name": "ask_user",
        "description": "Ask the user and wait for an answer. Use only for genuinely user-owned decisions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "header": {"type": "string"},
                            "question": {"type": "string"},
                            "options": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                    "required": ["label"],
                                },
                            },
                            "multiSelect": {"type": "boolean"},
                        },
                        "required": ["id", "header", "question", "options"],
                    },
                    "minItems": 1,
                    "maxItems": 3,
                },
                "timeoutSeconds": {"type": "number"},
            },
            "required": ["questions"],
        },
    }


def _get_session_key(session_key: str, agent_id: str) -> str:
    if session_key:
        return session_key
    if agent_id:
        return f"agent:{agent_id}"
    return "global"


def create_ask_user_tool(options: dict) -> AgentTool:
    gateway_call = options.get("gateway_call")
    session_key = options.get("session_key", "")
    agent_id = options.get("agent_id", "")
    resolved_session_key = _get_session_key(session_key, agent_id)

    definition = create_ask_user_tool_definition()

    async def _execute(
        tool_call_id: str, params: dict, signal: Any, on_update: Any
    ) -> Any:
        if not gateway_call:
            raise RuntimeError("ask_user tool requires gateway_call in options")

        questions = params.get("questions", [])
        if not isinstance(questions, list) or len(questions) == 0:
            raise ValueError("ask_user requires at least one question")
        if len(questions) > 3:
            raise ValueError("ask_user supports a maximum of 3 questions")

        raw_timeout = params.get("timeoutSeconds")
        if raw_timeout is None:
            timeout_sec = DEFAULT_ASK_USER_TIMEOUT_SECONDS
        else:
            timeout_sec = max(
                MIN_ASK_USER_TIMEOUT_SECONDS,
                min(MAX_ASK_USER_TIMEOUT_SECONDS, float(raw_timeout)),
            )
        timeout_ms = int(timeout_sec * 1000)

        # Check for existing questions for this session
        existing_question_id = None
        for qid, state in _ASK_USER_QUESTIONS.items():
            if state["session_key"] == resolved_session_key:
                existing_question_id = qid
                break

        if existing_question_id:
            raise ValueError(
                "ask_user already has a pending question for this session; wait for it to resolve before asking another"
            )

        question_id = tool_call_id
        state = {
            "session_key": resolved_session_key,
            "questions": questions,
            "expires_at_ms": int(time.time() * 1000) + timeout_ms,
        }
        _ASK_USER_QUESTIONS[question_id] = state

        cancellation_task: Optional[asyncio.Task] = None
        registered = False

        async def cancel_pending(reason: str) -> Optional[dict]:
            nonlocal cancellation_task
            if cancellation_task is None:
                async def _do_cancel():
                    try:
                        await gateway_call(
                            "question.resolve",
                            {"timeoutMs": ASK_USER_RPC_GRACE_MS},
                            {"id": question_id, "cancel": True, "resolvedBy": reason},
                        )
                        return None
                    except Exception:
                        # If already terminal, try to fetch answer
                        try:
                            res = await gateway_call(
                                "question.waitAnswer",
                                {"timeoutMs": ASK_USER_RPC_GRACE_MS},
                                {"id": question_id, "timeoutMs": 1000},
                            )
                            if isinstance(res, dict) and res.get("status") == "answered":
                                return res
                        except Exception:
                            pass
                        return None

                cancellation_task = asyncio.create_task(_do_cancel())
            return await cancellation_task

        def cancel_on_abort():
            if _ASK_USER_QUESTIONS.get(question_id) is state:
                _ASK_USER_QUESTIONS.pop(question_id, None)
            asyncio.create_task(cancel_pending("run-abort"))

        # In Python we may not have an identical event listener shape for signal,
        # but if we do we hook it here (stubbed for parity).
        if hasattr(signal, "addEventListener"):
            signal.addEventListener("abort", cancel_on_abort)
        elif hasattr(signal, "add_done_callback"):
            signal.add_done_callback(lambda _: cancel_on_abort())

        try:
            # 1. Register question
            req_params = {
                "id": question_id,
                "questions": questions,
                "timeoutMs": timeout_ms,
            }
            if agent_id:
                req_params["agentId"] = agent_id
            if session_key:
                req_params["sessionKey"] = session_key

            await gateway_call(
                "question.request",
                {},
                req_params,
                {"signal": signal} if signal else None,
            )
            registered = True

            # 2. Wait for answer
            wait_result = await gateway_call(
                "question.waitAnswer",
                {"timeoutMs": timeout_ms + ASK_USER_RPC_GRACE_MS},
                {"id": question_id, "timeoutMs": timeout_ms},
                {"signal": signal} if signal else None,
            )

            status = wait_result.get("status") if isinstance(wait_result, dict) else None

            if status == "pending":
                answered = await cancel_pending("wait-timeout")
                if answered:
                    return {"content": [{"type": "text", "text": json.dumps(answered)}]}
                return {"content": [{"type": "text", "text": '{"status": "no_answer"}'}]}

            if status == "answered":
                return {"content": [{"type": "text", "text": json.dumps(wait_result)}]}

            if status in ("expired", "cancelled"):
                return {"content": [{"type": "text", "text": '{"status": "no_answer"}'}]}

            raise ValueError("question.waitAnswer returned an invalid status")

        except Exception as e:
            if not registered or "QUESTION_ID_IN_USE" not in str(e):
                is_aborted = getattr(signal, "aborted", False) if signal else False
                reason = "run-abort" if is_aborted else ("tool-error" if registered else "registration-failed")
                answered = await cancel_pending(reason)
                if not is_aborted and answered:
                    return {"content": [{"type": "text", "text": json.dumps(answered)}]}
            raise
        finally:
            if hasattr(signal, "removeEventListener"):
                signal.removeEventListener("abort", cancel_on_abort)
            if _ASK_USER_QUESTIONS.get(question_id) is state:
                _ASK_USER_QUESTIONS.pop(question_id, None)

    definition["execute"] = _execute
    # Match AgentTool properties
    return {
        "name": definition["name"],
        "label": definition["name"],
        "description": definition["description"],
        "parameters": definition["inputSchema"],
        "execute": _execute,
    }


__all__ = ["create_ask_user_tool", "create_ask_user_tool_definition"]
