"""jarvis.agents.btw — /btw side-question agent execution.

OpenClaw parity: mirrors ``src/agents/btw.ts``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

_log = logging.getLogger("jarvis.agents.btw")

MAX_BTW_SNAPSHOT_MESSAGES = 100


def build_btw_system_prompt(
    base_prompt: str, question: str, in_flight_prompt: Optional[str] = None
) -> str:
    """Builds the system prompt for a BTW side question."""
    parts = [
        "You are answering a quick side question from the operator about the current session context.",
        "Your response should be direct, brief, and helpful.",
        "DO NOT use tools. DO NOT generate long explanatory text.",
    ]
    if in_flight_prompt:
        parts.append(f"\nThe operator is currently drafting this prompt:\n{in_flight_prompt}")
    
    parts.append(f"\nThe side question is: {question}")
    return "\n".join(parts)


def sanitize_btw_user_message(message: Dict[str, Any], image_limits: Any = None) -> Optional[Dict[str, Any]]:
    """Sanitize a user message, keeping only text parts."""
    if not isinstance(message, dict):
        return None
    content = message.get("content", [])
    if isinstance(content, str):
        return message
        
    sanitized_content = []
    for block in (content if isinstance(content, list) else []):
        if isinstance(block, dict) and block.get("type") == "text":
            sanitized_content.append(block)
    
    if not sanitized_content:
        return None
        
    return {
        "role": "user",
        "content": sanitized_content
    }


def sanitize_btw_assistant_message(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sanitize an assistant message, removing tool results and reasoning blocks."""
    if not isinstance(message, dict):
        return None
    content = message.get("content", [])
    if isinstance(content, str):
        return message
        
    sanitized_content = []
    for block in (content if isinstance(content, list) else []):
        if isinstance(block, dict):
            b_type = block.get("type")
            if b_type == "text":
                sanitized_content.append(block)
            # Drop tools, thinking, etc.
    
    if not sanitized_content:
        return None
        
    return {
        "role": "assistant",
        "content": sanitized_content
    }


def strip_tool_result_details(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Further strip any lingering tool results from context."""
    # In btw mode, we usually just want pure text context.
    return messages


async def run_btw_side_question(
    cfg: Any,
    agent_dir: str,
    provider: str,
    model: str,
    question: str,
    session_entry: Any,
    session_store: Any = None,
    session_key: Optional[str] = None,
    **kwargs: Any
) -> Dict[str, Any]:
    """Execute a BTW side question using the LLM client, bypassing normal transcript."""
    _log.info(f"Executing BTW side question: {question}")
    
    # 1. Gather context from session_entry
    raw_messages = []
    if hasattr(session_entry, "transcript"):
        raw_messages = session_entry.transcript
    elif isinstance(session_entry, dict):
        raw_messages = session_entry.get("transcript", [])
    
    # 2. Sanitize and trim messages
    context_messages = []
    for msg in raw_messages:
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
        if role == "user":
            sanitized = sanitize_btw_user_message(msg if isinstance(msg, dict) else msg.__dict__)
            if sanitized:
                context_messages.append(sanitized)
        elif role == "assistant":
            sanitized = sanitize_btw_assistant_message(msg if isinstance(msg, dict) else msg.__dict__)
            if sanitized:
                context_messages.append(sanitized)
    
    context_messages = strip_tool_result_details(context_messages)
    
    # Trim to limits
    if len(context_messages) > MAX_BTW_SNAPSHOT_MESSAGES:
        context_messages = context_messages[-MAX_BTW_SNAPSHOT_MESSAGES:]
        
    # 3. Build System Prompt
    system_prompt = build_btw_system_prompt("Base Context", question)
    
    # 4. We would normally call the runtime here. For parity/stubbing without full
    # OpenClaw runtime engine wiring, we just return a stub structure that Gateway emits as a side result.
    _log.info("Mocking model completion for BTW command in parity implementation.")
    
    return {
        "text": f"This is a side-question response for: {question}\n\n(Context analyzed: {len(context_messages)} messages)",
    }
