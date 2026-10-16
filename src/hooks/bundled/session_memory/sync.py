"""Post-compaction session memory sync.

Extracts the last user/assistant messages and saves them to <workspace>/memory/YYYY-MM-DD-HHMM.md.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

_log = logging.getLogger("jarvis.hooks.bundled.session_memory")


async def sync_session_memory_to_disk(
    config: Optional[Dict[str, Any]],
    session_key: Optional[str],
    session_id: Optional[str],
    agent_id: Optional[str],
    session_file: str,
) -> None:
    """Save the recent conversation transcript to disk."""
    if not session_key:
        return

    try:
        from src.sessions.history_store import ConversationHistoryStore
        store = ConversationHistoryStore()
        turns = store.get_turns(session_key)
    except Exception as e:
        _log.warning("Failed to fetch conversation history for memory sync: %s", e)
        return

    if not turns:
        return

    filtered_turns = [t for t in turns if t.get("role") in ("user", "assistant")]
    
    msg_count = 15
    if config and "hooks.internal.entries.session-memory.messages" in config:
        try:
            msg_count = int(config["hooks.internal.entries.session-memory.messages"])
        except (ValueError, TypeError):
            pass

    recent_turns = filtered_turns[-msg_count:] if msg_count > 0 else filtered_turns
    
    md_lines = []
    for turn in recent_turns:
        role = "User" if turn["role"] == "user" else "Assistant"
        content = turn["content"]
        md_lines.append(f"**{role}:**\n{content}\n")
        
    md_content = "\n".join(md_lines)
    
    # We fallback to ~/.jarvis/memory if workspace.dir isn't mapped
    workspace_dir = os.environ.get("JARVIS_WORKSPACE_DIR", os.path.expanduser("~/.jarvis"))
    
    memory_dir = Path(workspace_dir) / "memory"
    try:
        memory_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        _log.warning("Could not create memory directory %s: %s", memory_dir, e)
        return
    
    timestamp = datetime.utcnow().strftime("%Y-%m-%d-%H%M")
    
    # We use timestamp since LLM slug generation is optional
    filename = f"{timestamp}.md"
    file_path = memory_dir / filename
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("# Session Transcript\n\n")
            f.write(f"Session Key: {session_key}\n")
            if session_id:
                f.write(f"Session ID: {session_id}\n")
            if agent_id:
                f.write(f"Agent ID: {agent_id}\n")
            f.write("\n")
            f.write(md_content)
        _log.debug("Session memory saved to %s", file_path)
    except Exception as e:
        _log.warning("Failed to write session memory to %s: %s", file_path, e)
