"""jarvis.agents.sessions.tools.session_tools — session-state tools.

OpenClaw parity: mirrors OpenClaw's session-state awareness tools
(`sessions_send`, `session_status`, `sessions_list`).
"""
from __future__ import annotations

import logging
from typing import Any

from ..extensions.types import AgentToolResult, ToolDefinition
from .tool_definition_wrapper import AgentTool
from src.sessions.session_store import get_default_session_store
from src.sessions.session_state_events import (
    list_session_state_events_since,
    register_session_state_watch,
    record_session_state_event,
)
from src.agents.sessions.session_manager_id import create_session_id

logger = logging.getLogger("jarvis.agents.sessions.tools.session_tools")


# ============================================================================
# sessions_list
# ============================================================================


def create_sessions_list_tool_definition() -> ToolDefinition:
    """Create the sessions_list tool definition."""
    return {
        "name": "sessions_list",
        "description": "List available sessions for cross-session coordination.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    }


async def run_sessions_list_tool(args: dict, context: Any) -> AgentToolResult:
    store = get_default_session_store()
    if store is None:
        return {"content": [{"type": "text", "text": "Session store is not initialized."}], "isError": True}
        
    sessions = store.list_sessions()
    
    # Exclude current session and list active ones
    current_key = context.get_session_manager().get_session_id() if hasattr(context, "get_session_manager") else None
    
    result = []
    for s in sessions:
        if s.session_key != current_key:
            # We can also get the latest stateVersion by listing events
            # For brevity, we just return basic info
            result.append({
                "sessionKey": s.session_key,
                "agentId": s.agent_id,
                "kind": s.kind,
                "updatedAt": s.updated_at
            })
            
    import json
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


def create_sessions_list_tool() -> AgentTool:
    tool = create_sessions_list_tool_definition()
    tool["execute"] = run_sessions_list_tool
    return tool

# ============================================================================
# session_status
# ============================================================================


def create_session_status_tool_definition() -> ToolDefinition:
    """Create the session_status tool definition."""
    return {
        "name": "session_status",
        "description": "Pull state deltas for a watched session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sessionKey": {"type": "string", "description": "The target session key"},
                "changesSince": {"type": "number", "description": "The last seen stateVersion"}
            },
            "required": ["sessionKey", "changesSince"],
        },
    }


async def run_session_status_tool(args: dict, context: Any) -> AgentToolResult:
    session_key = args.get("sessionKey")
    changes_since = args.get("changesSince", 0)
    
    if not session_key:
        return {"content": [{"type": "text", "text": "Missing sessionKey"}], "isError": True}
        
    events = list_session_state_events_since(session_key, int(changes_since))
    
    latest_version = changes_since
    if events:
        latest_version = max(e.event_id for e in events)
        
    event_dicts = [
        {
            "eventId": e.event_id,
            "kind": e.kind,
            "payload": e.payload,
            "createdAt": e.created_at
        } for e in events
    ]
    
    import json
    return {
        "content": [{
            "type": "text", 
            "text": json.dumps({
                "stateVersion": latest_version,
                "stateChanges": {"events": event_dicts}
            }, indent=2)
        }]
    }


def create_session_status_tool() -> AgentTool:
    tool = create_session_status_tool_definition()
    tool["execute"] = run_session_status_tool
    return tool


# ============================================================================
# sessions_send
# ============================================================================


def create_sessions_send_tool_definition() -> ToolDefinition:
    """Create the sessions_send tool definition."""
    return {
        "name": "sessions_send",
        "description": "Send a message to another session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "targetSessionKey": {"type": "string"},
                "message": {"type": "string"},
                "watch": {"type": "boolean", "default": False}
            },
            "required": ["targetSessionKey", "message"],
        },
    }


async def run_sessions_send_tool(args: dict, context: Any) -> AgentToolResult:
    target_key = args.get("targetSessionKey")
    message = args.get("message")
    watch = args.get("watch", False)
    
    if not target_key or not message:
        return {"content": [{"type": "text", "text": "Missing targetSessionKey or message"}], "isError": True}
        
    store = get_default_session_store()
    if store is None:
        return {"content": [{"type": "text", "text": "Session store is not initialized."}], "isError": True}
        
    current_key = context.get_session_manager().get_session_id() if hasattr(context, "get_session_manager") else "unknown"
    
    if watch and current_key != "unknown":
        register_session_state_watch(target_key, current_key)
        
    # Append message to target session
    try:
        from jarvis.sessions.session_store import _now_iso
        now = _now_iso()
        entry = {
            "id": create_session_id(),
            "kind": "user_message",
            "payload": {"text": message},
            "timestamp": now,
        }
        store.append_entry(target_key, entry)
        
        # Notify watchers
        record_session_state_event(
            session_key=target_key,
            actor_id=current_key,
            actor_type="agent",
            kind="message",
            payload={"text": message}
        )
        
        return {"content": [{"type": "text", "text": f"Message sent to {target_key}."}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Failed to send message: {e}"}], "isError": True}


def create_sessions_send_tool() -> AgentTool:
    tool = create_sessions_send_tool_definition()
    tool["execute"] = run_sessions_send_tool
    return tool
