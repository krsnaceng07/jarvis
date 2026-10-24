"""jarvis.agents.decision.tool_selection — Tool selection, argument preflight, and loop protection.

OpenClaw parity: Selects appropriate tools based on analyzed intent,
preflights and repairs arguments, and intervenes on repeated failure loops.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional

from .intent import AnalyzedIntent


@dataclass(slots=True)
class ToolSelectionPlan:
    tool_name: str
    arguments: dict[str, Any]
    reason: str
    confidence: float = 1.0


class ToolLoopInterventionError(Exception):
    """Raised when an identical tool call repeats beyond safety threshold."""


class ToolSelector:
    """Selects tools, normalizes arguments, and prevents tool execution loops."""

    def __init__(self, max_identical_calls: int = 2) -> None:
        self.max_identical_calls = max_identical_calls
        self._call_history: list[str] = []

    def check_loop_intervention(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Fingerprints the tool call and raises if loop threshold is exceeded."""
        fingerprint = self._compute_fingerprint(tool_name, arguments)
        self._call_history.append(fingerprint)

        recent = self._call_history[-(self.max_identical_calls + 1) :]
        if len(recent) > self.max_identical_calls and all(fp == fingerprint for fp in recent):
            # Prune the streak so subsequent replanned turns are not permanently poisoned
            self._call_history = [fp for fp in self._call_history if fp != fingerprint]
            raise ToolLoopInterventionError(
                f"Tool loop detected: '{tool_name}' was invoked with identical arguments "
                f"{self.max_identical_calls + 1} times in succession. Execution paused for replanning."
            )

    def reset(self) -> None:
        """Reset the call history on new session or turn."""
        self._call_history.clear()

    def record_outcome(self, tool_name: str, arguments: dict[str, Any], result: Any = None) -> None:
        """Record the outcome of a tool execution for loop protection and telemetry."""
        fingerprint = self._compute_fingerprint(tool_name, arguments)
        if not self._call_history or self._call_history[-1] != fingerprint:
            self._call_history.append(fingerprint)

    def select_tool_for_intent(
        self, intent: AnalyzedIntent, available_tools: set[str]
    ) -> Optional[ToolSelectionPlan]:
        """Selects the primary tool and prepares repaired arguments based on intent."""
        if not intent.is_actionable or not intent.primary_tool:
            return None

        tool_name = intent.primary_tool
        if tool_name not in available_tools:
            return None

        args = dict(intent.parameters)
        repaired_args = self.preflight_arguments(tool_name, args)

        return ToolSelectionPlan(
            tool_name=tool_name,
            arguments=repaired_args,
            reason=f"Selected {tool_name} to satisfy intent: {intent.category.value}",
            confidence=intent.confidence,
        )

    def preflight_arguments(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Preflights and sanitizes arguments according to OpenClaw standards."""
        cleaned = dict(args)

        # 1. Normalize all string values to Unicode NFC
        for k, v in list(cleaned.items()):
            if isinstance(v, str):
                cleaned[k] = unicodedata.normalize("NFC", v.strip())

        # 2. Path normalization for filesystem & open_path tools
        if tool_name in (
            "mkdir",
            "remove_path",
            "rename_path",
            "read",
            "write",
            "edit",
            "open_path",
        ):
            for p_key in ("path", "old_path", "new_path", "target"):
                if p_key in cleaned and isinstance(cleaned[p_key], str):
                    val = cleaned[p_key]
                    # Fix double slashes and normalize separators
                    norm = re.sub(r"[/\\]+", "/", val)
                    norm = re.sub(r"^([a-zA-Z]):/+", r"\1:/", norm)
                    # Don't convert single-word app targets like "notepad", "calc", "explorer" into paths
                    if (
                        tool_name == "open_path"
                        and p_key == "target"
                        and "/" not in norm
                        and "\\" not in val
                    ):
                        cleaned[p_key] = val.strip()
                    else:
                        cleaned[p_key] = norm

        # 3. Process action normalization
        if tool_name == "process":
            action = cleaned.get("action", "kill")
            if action in ("close", "terminate", "stop"):
                cleaned["action"] = "kill"
            if "session_id" in cleaned and isinstance(cleaned["session_id"], str):
                # Clean app name
                app = cleaned["session_id"].strip().lower()
                app = re.sub(r"\.exe$", "", app)
                cleaned["session_id"] = app

        # 4. Browser search URL preparation
        if tool_name == "browser" and "query" in cleaned:
            query = cleaned.pop("query")
            engine = cleaned.pop("engine", "web")
            import urllib.parse

            encoded = urllib.parse.quote_plus(query)
            if "youtube" in engine:
                cleaned["action"] = "open"
                cleaned["url"] = f"https://www.youtube.com/results?search_query={encoded}"
            else:
                cleaned["action"] = "open"
                cleaned["url"] = f"https://www.google.com/search?q={encoded}"

        return cleaned

    @classmethod
    def _compute_fingerprint(cls, tool_name: str, arguments: dict[str, Any]) -> str:
        try:
            ser = json.dumps(arguments, sort_keys=True, default=str)
        except Exception:
            ser = str(arguments)
        data = f"{tool_name}:{ser}".encode("utf-8")
        return hashlib.sha256(data).hexdigest()[:16]
