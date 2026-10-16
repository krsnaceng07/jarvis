"""Desktop tool-loop guard.

Keeps the OpenClaw-style loop detector out of the desktop app entrypoint while
preserving the same per-session behavior.
"""

from __future__ import annotations

from typing import Any


class ToolLoopGuard:
    """Per-session tool loop detection guard."""

    _LOOP_CONFIG: dict[str, Any] = {
        "enabled": True,
        "historySize": 30,
        "warningThreshold": 10,
        "unknownToolThreshold": 10,
        "criticalThreshold": 20,
        "globalCircuitBreakerThreshold": 30,
        "detectors": {
            "genericRepeat": True,
            "knownPollNoProgress": True,
            "pingPong": True,
        },
    }

    def __init__(self) -> None:
        self._state: dict[str, Any] = {}
        self.critical_tool_loop_seen: bool = False

    def reset(self) -> None:
        self._state = {}
        self.critical_tool_loop_seen = False

    def check_before(self, tool_name: str, args: dict[str, Any], tool_call_id: str) -> str | None:
        from src.agents.tool_loop_detection import detect_tool_call_loop, record_tool_call

        record_tool_call(
            self._state,
            tool_name,
            args,
            tool_call_id=tool_call_id,
            config=self._LOOP_CONFIG,
        )
        result = detect_tool_call_loop(self._state, tool_name, args, config=self._LOOP_CONFIG)
        if result.get("stuck"):
            level = result.get("level", "warning")
            message = result.get("message", "Tool loop detected.")
            if level == "critical":
                self.critical_tool_loop_seen = True
                print(f"[JARVIS] 🔴 Tool loop CRITICAL ({tool_name}): {message[:100]}")
                return (
                    f"[TOOL LOOP BLOCKED] {message}\n\n"
                    "Do not repeat this exact tool action. Reassess the task. You may answer the user, "
                    "ask for clarification, or continue with a different tool or different arguments."
                )
            print(f"[JARVIS] ⚠️ Tool loop WARNING ({tool_name}): {message[:100]}")
        return None

    def record_outcome(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: str | None,
        error: str | None,
        tool_call_id: str,
    ) -> None:
        from src.agents.tool_loop_detection import record_tool_call_outcome

        result_payload: dict[str, Any] | None = (
            {"content": [{"type": "text", "text": result}]} if result is not None else None
        )
        record_tool_call_outcome(
            self._state,
            {
                "toolName": tool_name,
                "toolParams": args,
                "toolCallId": tool_call_id,
                "result": result_payload,
                "error": error,
                "config": self._LOOP_CONFIG,
            },
        )


__all__ = ["ToolLoopGuard"]
