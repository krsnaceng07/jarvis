---
name: command-logger
description: "Logs all commands to ~/.jarvis/logs/commands.log"
events: ["command"]
---

# Command Logger Hook

This hook logs every slash command as a JSON line (timestamp, action, session key, sender ID, source) to `~/.jarvis/logs/commands.log`.
