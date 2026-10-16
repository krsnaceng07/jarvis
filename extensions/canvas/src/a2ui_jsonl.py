"""A2UI JSONL message stream parser and formatter for Canvas widgets."""

from __future__ import annotations

import json
from typing import Any


def parse_a2ui_jsonl(raw_text: str) -> list[dict[str, Any]]:
    """Parse newline-delimited JSON messages."""
    events: list[dict[str, Any]] = []
    for line in raw_text.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        try:
            parsed = json.loads(line_str)
            if isinstance(parsed, dict):
                events.append(parsed)
        except json.JSONDecodeError:
            continue
    return events


def format_a2ui_jsonl(events: list[dict[str, Any]]) -> str:
    """Format events into newline-delimited JSON string."""
    return "\n".join(json.dumps(event) for event in events)
