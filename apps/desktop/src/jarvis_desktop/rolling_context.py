"""Rolling session context and transcript resumption manager for JARVIS desktop.

Maintains a bounded sliding-window ring buffer of recent conversation turns and
tool executions across Gemini Live WebSocket reconnections, GoAway server rotations,
and wake-from-standby transitions to prevent mid-conversation amnesia.
"""

from __future__ import annotations

import collections
import json
import time
from typing import Any


class RollingSessionContext:
    """Bounded sliding-window history for session continuity and prompt injection."""

    def __init__(self, max_turns: int = 16) -> None:
        self.max_turns = max_turns
        self._turns: collections.deque[dict[str, Any]] = collections.deque(maxlen=max_turns)
        self.latest_resumption_handle: str | None = None

    def record_user_turn(self, text: str) -> None:
        """Record a completed user speech or text turn."""
        cleaned = text.strip() if text else ""
        if not cleaned:
            return
        self._turns.append(
            {
                "role": "user",
                "text": cleaned,
                "timestamp": time.time(),
            }
        )

    def record_model_turn(self, text: str) -> None:
        """Record a completed model response turn."""
        cleaned = text.strip() if text else ""
        if not cleaned:
            return
        self._turns.append(
            {
                "role": "assistant",
                "text": cleaned,
                "timestamp": time.time(),
            }
        )

    def record_tool_execution(
        self, tool_name: str, args: dict[str, Any] | None, summary_result: str
    ) -> None:
        """Record an executed tool invocation and its compact outcome."""
        res_summary = (summary_result or "").strip()
        if len(res_summary) > 300:
            res_summary = res_summary[:297] + "..."
        self._turns.append(
            {
                "role": "tool",
                "name": tool_name,
                "args": dict(args or {}),
                "result": res_summary,
                "timestamp": time.time(),
            }
        )

    def format_rolling_context_for_prompt(self, max_chars: int = 4000) -> str:
        """Format the recent sliding-window turns into a markdown prompt block.

        Automatically trims older turns from the head if the formatted text
        exceeds max_chars budget.
        """
        if not self._turns:
            return ""

        header = (
            "\n### RECENT SESSION CONTINUITY (ROLLING WINDOW):\n"
            "The live voice connection was recently resumed/reconnected. "
            "Maintain natural conversational continuity with the recent user interactions and tool executions below:\n"
        )

        turn_lines: list[str] = []
        for item in self._turns:
            role = item.get("role")
            if role == "user":
                turn_lines.append(f"- [User]: {item['text']}")
            elif role == "assistant":
                turn_lines.append(f"- [Jarvis]: {item['text']}")
            elif role == "tool":
                args_str = json.dumps(item.get("args", {}), ensure_ascii=False)
                if len(args_str) > 120:
                    args_str = args_str[:117] + "..."
                turn_lines.append(f"- [Tool Executed]: {item['name']}({args_str}) → {item['result']}")

        # Truncate oldest turns if exceeding max_chars budget
        while turn_lines:
            content = "\n".join(turn_lines)
            full_block = header + content + "\n"
            if len(full_block) <= max_chars:
                return full_block
            turn_lines.pop(0)

        return ""

    def clear(self) -> None:
        """Reset all recorded turns and resumption handles."""
        self._turns.clear()
        self.latest_resumption_handle = None

    def get_turns_count(self) -> int:
        """Return count of currently buffered turns."""
        return len(self._turns)

    def get_turns(self) -> list[dict[str, Any]]:
        """Return a copy of the buffered turns list."""
        return list(self._turns)


__all__ = ["RollingSessionContext"]
