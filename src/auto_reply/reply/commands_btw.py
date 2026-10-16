"""jarvis.auto_reply.reply.commands_btw — /btw side-question command handler.

OpenClaw parity: mirrors ``src/auto-reply/reply/commands-btw.ts``.
"""

from __future__ import annotations

import logging
from typing import Any

from .btw_command import extract_btw_question

_log = logging.getLogger("jarvis.auto_reply.commands_btw")

BTW_USAGE = "Usage: /btw [side question]"


async def handle_btw_command(params: Any, allow_text_commands: bool) -> dict[str, Any] | None:
    """Command handler for /btw side questions."""
    if not allow_text_commands:
        return None

    # Try to extract the btw question
    command_body_normalized = getattr(params.command, "commandBodyNormalized", "")
    if not command_body_normalized and isinstance(params.command, dict):
        command_body_normalized = params.command.get("commandBodyNormalized", "")

    question = extract_btw_question(command_body_normalized)
    
    # Not a btw command
    if question is None:
        return None

    # In Python we assume unauthorized checking is done earlier or we can stub it
    # unauthorized = rejectUnauthorizedCommand(params, "/btw")
    
    if not question:
        return {
            "shouldContinue": False,
            "reply": {"text": BTW_USAGE},
        }

    # Grab the session
    session_store = getattr(params, "sessionStore", {})
    if not session_store and isinstance(params, dict):
        session_store = params.get("sessionStore", {})
        
    session_key = getattr(params, "sessionKey", None) or (params.get("sessionKey") if isinstance(params, dict) else None)
    session_entry = getattr(params, "sessionEntry", None) or (params.get("sessionEntry") if isinstance(params, dict) else None)

    target_session_entry = session_store.get(session_key) if session_key and session_store else session_entry

    if not target_session_entry or not (getattr(target_session_entry, "sessionId", None) or (isinstance(target_session_entry, dict) and target_session_entry.get("sessionId"))):
        return {
            "shouldContinue": False,
            "reply": {"text": "?? /btw requires an active session with existing context."},
        }

    # At this point, we'd resolve the agent directory and execute the btw side question.
    # We will import run_btw_side_question lazily to avoid circular imports.
    from src.agents.btw import run_btw_side_question

    try:
        reply = await run_btw_side_question(
            cfg=getattr(params, "cfg", {}),
            agent_dir=getattr(params, "agentDir", ""),
            provider=getattr(params, "provider", ""),
            model=getattr(params, "model", ""),
            question=question,
            session_entry=target_session_entry,
            session_store=session_store,
            session_key=session_key
        )
        if reply:
            reply["btw"] = {"question": question}
            
        return {
            "shouldContinue": False,
            "reply": reply,
        }
    except Exception as e:
        msg = str(e).strip()
        _log.warning("btw command failed: %s", msg)
        return {
            "shouldContinue": False,
            "reply": {
                "text": f"?? /btw failed{': ' + msg if msg else '.'}",
                "btw": {"question": question},
                "isError": True,
            }
        }
