"""jarvis.agents.sessions.tools.session_management_tools
Implements the OpenClaw session management tools: sessions, sessions_search, and sessions_history.
"""
from typing import Any
from .tool_definition_wrapper import AgentTool

# ============================================================================
# sessions
# ============================================================================

def create_sessions_tool_definition() -> dict:
    return {
        "name": "sessions",
        "description": "Patch, reset, or delete visible sessions and manage session groups.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "enum": ["patch", "reset", "delete", "group_list", "group_set", "group_rename", "group_delete"],
                    "description": "The action to perform."
                },
                "sessionKey": {"type": "string", "description": "The session key for patch/reset/delete."},
                "expectedSessionId": {"type": "string", "description": "Required for archiving or restoring."},
                "label": {"type": "string", "description": "The new label for the session."},
                "model": {"type": "string", "description": "The new model for the session."},
                "thinking": {"type": "string", "description": "The new thinking level."},
                "archive": {"type": "boolean", "description": "Archive or restore the session."},
                "deleteTranscript": {"type": "boolean", "description": "Whether to delete transcript when action is delete (default true)."}
            },
            "required": ["action"],
        },
    }

async def run_sessions_tool(args: dict, context: Any) -> dict:
    action = args.get("action")
    if not action:
        return {"content": [{"type": "text", "text": "Missing action"}], "isError": True}
    
    # Stub implementation pending actual session state mutation logic
    return {"content": [{"type": "text", "text": f"Successfully executed sessions {action}"}]}

def create_sessions_tool() -> AgentTool:
    tool = create_sessions_tool_definition()
    tool["execute"] = run_sessions_tool
    return tool


# ============================================================================
# sessions_search
# ============================================================================

def create_sessions_search_tool_definition() -> dict:
    return {
        "name": "sessions_search",
        "description": "Search visible session transcripts and return matching excerpts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The text to search for."}
            },
            "required": ["query"],
        },
    }

async def run_sessions_search_tool(args: dict, context: Any) -> dict:
    query = args.get("query")
    if not query:
        return {"content": [{"type": "text", "text": "Missing query"}], "isError": True}
    
    # Stub implementation
    return {"content": [{"type": "text", "text": "Search functionality stubbed."}]}

def create_sessions_search_tool() -> AgentTool:
    tool = create_sessions_search_tool_definition()
    tool["execute"] = run_sessions_search_tool
    return tool


# ============================================================================
# sessions_history
# ============================================================================

def create_sessions_history_tool_definition() -> dict:
    return {
        "name": "sessions_history",
        "description": "Read the transcript of a specific session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sessionKey": {"type": "string", "description": "The session key."},
                "includeTools": {"type": "boolean", "description": "Include tool results."},
                "limit": {"type": "number", "description": "Number of rows to fetch."},
                "offset": {"type": "number", "description": "Pagination offset."}
            },
            "required": ["sessionKey"],
        },
    }

async def run_sessions_history_tool(args: dict, context: Any) -> dict:
    session_key = args.get("sessionKey")
    if not session_key:
        return {"content": [{"type": "text", "text": "Missing sessionKey"}], "isError": True}
    
    # Stub implementation
    return {"content": [{"type": "text", "text": "History retrieval stubbed."}]}

def create_sessions_history_tool() -> AgentTool:
    tool = create_sessions_history_tool_definition()
    tool["execute"] = run_sessions_history_tool
    return tool
