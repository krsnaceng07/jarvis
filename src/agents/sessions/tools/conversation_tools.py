"""jarvis.agents.sessions.tools.conversation_tools
Implements the OpenClaw conversation tools: conversations_list, conversations_send, and conversations_turn.
"""
from typing import Any
from .tool_definition_wrapper import AgentTool

# ============================================================================
# conversations_list
# ============================================================================

def create_conversations_list_tool_definition() -> dict:
    return {
        "name": "conversations_list",
        "description": "List stable external conversation addresses.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "The specific channel to list addresses for."},
                "query": {"type": "string", "description": "Query to find a specific peer."}
            },
            "required": [],
        },
    }

async def run_conversations_list_tool(args: dict, context: Any) -> dict:
    # Stub implementation
    return {"content": [{"type": "text", "text": "Conversations list stubbed."}]}

def create_conversations_list_tool() -> AgentTool:
    tool = create_conversations_list_tool_definition()
    tool["execute"] = run_conversations_list_tool
    return tool


# ============================================================================
# conversations_send
# ============================================================================

def create_conversations_send_tool_definition() -> dict:
    return {
        "name": "conversations_send",
        "description": "Send a message to an exact external conversation without running a local session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversationRef": {"type": "string", "description": "Opaque reference to the conversation."},
                "message": {"type": "string", "description": "The message to send."}
            },
            "required": ["conversationRef", "message"],
        },
    }

async def run_conversations_send_tool(args: dict, context: Any) -> dict:
    # Stub implementation
    return {"content": [{"type": "text", "text": "Conversations send stubbed."}]}

def create_conversations_send_tool() -> AgentTool:
    tool = create_conversations_send_tool_definition()
    tool["execute"] = run_conversations_send_tool
    return tool


# ============================================================================
# conversations_turn
# ============================================================================

def create_conversations_turn_tool_definition() -> dict:
    return {
        "name": "conversations_turn",
        "description": "Send a message to an exact external conversation and wait for its correlated reply.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversationRef": {"type": "string", "description": "Opaque reference to the conversation."},
                "message": {"type": "string", "description": "The message to send."},
                "timeoutSeconds": {"type": "number", "description": "Timeout to wait for reply."}
            },
            "required": ["conversationRef", "message"],
        },
    }

async def run_conversations_turn_tool(args: dict, context: Any) -> dict:
    # Stub implementation
    return {"content": [{"type": "text", "text": "Conversations turn stubbed."}]}

def create_conversations_turn_tool() -> AgentTool:
    tool = create_conversations_turn_tool_definition()
    tool["execute"] = run_conversations_turn_tool
    return tool
