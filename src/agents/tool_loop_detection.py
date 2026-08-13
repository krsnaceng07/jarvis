"""Tool loop detector — mirrors OpenClaw loop detection mechanism."""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from typing import Any

_log = logging.getLogger("jarvis.agents.tool_loop_detection")


@dataclass(frozen=True, slots=True)
class ToolCallSignature:
    tool_name: str
    args_json: str


class ToolLoopDetectedError(RuntimeError):
    """Raised when an infinite tool call loop is detected."""
    pass


class ToolLoopDetector:
    """Sliding window loop detector for tool executions."""

    def __init__(self, window_size: int = 5, threshold: int = 3) -> None:
        self.window_size = window_size
        self.threshold = threshold
        self._history: deque[ToolCallSignature] = deque(maxlen=window_size)

    def record_and_check(self, tool_name: str, args: dict[str, Any] | None = None) -> bool:
        """Record a tool execution. Return True if loop detected, False otherwise."""
        try:
            args_str = json.dumps(args or {}, sort_keys=True)
        except Exception:
            args_str = str(args)

        sig = ToolCallSignature(tool_name, args_str)
        self._history.append(sig)

        count = sum(1 for item in self._history if item == sig)
        if count >= self.threshold:
            _log.warning("Tool loop detected for tool '%s' (%d repeated calls)", tool_name, count)
            return True
        return False

    def check_or_raise(self, tool_name: str, args: dict[str, Any] | None = None) -> None:
        if self.record_and_check(tool_name, args):
            raise ToolLoopDetectedError(
                f"Loop detected: Tool '{tool_name}' called repeatedly with identical parameters."
            )

    def reset(self) -> None:
        self._history.clear()


__all__ = ["ToolCallSignature", "ToolLoopDetectedError", "ToolLoopDetector"]
