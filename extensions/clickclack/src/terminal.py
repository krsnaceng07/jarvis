"""ClickClack terminal command models and ANSI progress formatters."""

from __future__ import annotations

from typing import Any


def format_terminal_progress(step: int, total: int, status: str) -> str:
    """Format an interactive terminal progress bar string."""
    pct = int((step / max(1, total)) * 100)
    bar = "=" * (pct // 5) + ">" + " " * (20 - (pct // 5))
    return f"[{bar}] {pct}% - {status}"


def parse_terminal_command(raw_input: str) -> dict[str, Any]:
    """Parse interactive terminal commands."""
    trimmed = raw_input.strip()
    if trimmed.startswith("/"):
        parts = trimmed[1:].split(" ", 1)
        return {
            "is_command": True,
            "command": parts[0],
            "args": parts[1] if len(parts) > 1 else "",
        }
    return {
        "is_command": False,
        "command": "",
        "args": trimmed,
    }
