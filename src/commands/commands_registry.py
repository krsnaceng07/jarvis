"""jarvis.commands.commands_registry — Command Registry & Directive Handling.

OpenClaw parity: mirrors
``openclaw-main/docs/tools/commands.md`` and
``openclaw-main/src/auto-reply/commands-registry.types.ts``.

Three command types:
1. Commands: Standalone `/...` messages handled by Gateway.
2. Directives: `/think`, `/fast`, `/verbose`, `/trace`, `/reasoning`, `/elevated`, `/exec`, `/model`, `/queue`.
3. Inline shortcuts: `/help`, `/commands`, `/status`, `/whoami`.

Features:
- `DIRECTIVES`: Set of canonical directive names.
- `INLINE_SHORTCUTS`: Set of canonical inline shortcut names.
- `CommandsConfig`: Configuration dataclass for commands options.
- `extract_directives_and_shortcuts()`: Strips directives/shortcuts and extracts session hints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

CommandScope = Literal["text", "native", "both"]
CommandTier = Literal["essential", "standard", "power"]
CommandCategory = Literal["session", "options", "status", "management", "media", "tools", "docks"]

DIRECTIVES: set[str] = {
    "think",
    "thinking",
    "t",
    "fast",
    "verbose",
    "v",
    "trace",
    "reasoning",
    "reason",
    "elevated",
    "elev",
    "exec",
    "model",
    "queue",
}

INLINE_SHORTCUTS: set[str] = {
    "help",
    "commands",
    "status",
    "whoami",
    "id",
    "btw",
    "side",
}


@dataclass
class CommandsConfig:
    text: bool = True
    native: str | bool = "auto"
    nativeSkills: str | bool = "auto"
    bash: bool = False
    bashForegroundMs: int = 2000
    config: bool = False
    mcp: bool = False
    plugins: bool = False
    debug: bool = False
    restart: bool = True
    ownerAllowFrom: list[str] = field(default_factory=list)
    allowFrom: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class ParsedDirectivesResult:
    cleaned_text: str
    directives_found: dict[str, str]
    is_directive_only: bool


def extract_directives_and_shortcuts(message: str) -> ParsedDirectivesResult:
    """Extract directives/shortcuts from message and return cleaned prompt text."""
    trimmed = message.strip()
    directives_found: dict[str, str] = {}

    if not trimmed:
        return ParsedDirectivesResult(cleaned_text="", directives_found={}, is_directive_only=False)

    tokens = trimmed.split()
    cleaned_tokens: list[str] = []
    directive_count = 0

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("/"):
            match = re.match(r"^/([a-zA-Z0-9_-]+)(?::(.*)|=(.*))?$", token)
            if match:
                cmd_name = match.group(1).lower()
                cmd_val = match.group(2) or match.group(3)
                
                if cmd_name in DIRECTIVES:
                    if not cmd_val:
                        # Check if next token exists and doesn't start with /
                        if i + 1 < len(tokens) and not tokens[i+1].startswith("/"):
                            cmd_val = tokens[i+1]
                            i += 1
                        else:
                            cmd_val = "true"
                    directives_found[cmd_name] = cmd_val
                    directive_count += 1
                    i += 1
                    continue
                elif cmd_name in INLINE_SHORTCUTS:
                    cmd_val = cmd_val or "true"
                    directives_found[cmd_name] = cmd_val
                    i += 1
                    continue

        cleaned_tokens.append(token)
        i += 1

    cleaned_text = " ".join(cleaned_tokens)
    is_directive_only = (directive_count > 0 and len(cleaned_tokens) == 0)

    return ParsedDirectivesResult(
        cleaned_text=cleaned_text,
        directives_found=directives_found,
        is_directive_only=is_directive_only,
    )


__all__ = [
    "DIRECTIVES",
    "INLINE_SHORTCUTS",
    "CommandCategory",
    "CommandScope",
    "CommandTier",
    "CommandsConfig",
    "ParsedDirectivesResult",
    "extract_directives_and_shortcuts",
]
