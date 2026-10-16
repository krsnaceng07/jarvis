import json
import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger("jarvis.hooks.command_logger")

def handle(event: Any) -> None:
    """Logs command events to ~/.jarvis/logs/commands.log."""
    if event.type != "command":
        return

    try:
        # Default logs dir in Jarvis is ~/.jarvis/logs
        log_dir = Path.home() / ".jarvis" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / "commands.log"
        
        entry = {
            "timestamp": event.timestamp,
            "action": event.action,
            "sessionKey": event.session_key,
            "senderId": event.context.get("senderId"),
            "source": event.context.get("commandSource"),
        }
        
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
            
    except Exception as e:
        _log.warning("failed to log command: %s", e)
