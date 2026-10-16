"""jarvis.auto_reply.reply.btw_command — /btw side-question regex parsing.

OpenClaw parity: mirrors ``src/auto-reply/reply/btw-command.ts``.
"""

import re

# Matches "/btw" or "/side" at the start of the string, case-insensitive,
# followed by a colon, whitespace, or end of string.
BTW_COMMAND_RE = re.compile(r"^/(btw|side)(?::|\s|$)", re.IGNORECASE)

def is_btw_request_text(text: str | None) -> bool:
    """Returns True if the text is a /btw or /side command."""
    if not text:
        return False
    normalized = text.strip()
    return bool(BTW_COMMAND_RE.match(normalized))

def extract_btw_question(text: str | None) -> str | None:
    """Extracts the question part from a /btw or /side command.
    Returns None if the text is not a btw command.
    """
    if not text:
        return None
    normalized = text.strip()
    match = re.match(r"^/(btw|side)(?:\s+(.*))?$", normalized, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return (match.group(2) or "").strip()
