"""jarvis_learning.models.arguments — deterministic argument construction.

Separates tool classification from parameter generation. Small local models
never synthesize freeform shell commands, file paths, or URLs. Parameters
are extracted deterministically from verified context or delegated to Gemini.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ArgumentBuildResult:
    """Result of argument synthesis."""

    success: bool
    arguments: dict[str, Any]
    requires_llm: bool
    reason: str


class DeterministicArgumentBuilder:
    """Builds valid tool arguments from structured runtime context."""

    def build_arguments(
        self,
        tool_name: str,
        user_input: str,
        context: dict[str, Any],
    ) -> ArgumentBuildResult:
        """Construct arguments based on known tool schemas."""
        # 1. Browser tab navigation
        if tool_name == "browser.navigate_tab":
            open_tabs = context.get("open_tabs", [])
            # If target tab id is present in context
            tab_id = context.get("tab_id")
            if tab_id is not None:
                return ArgumentBuildResult(
                    success=True,
                    arguments={"tab_id": tab_id},
                    requires_llm=False,
                    reason="tab_id extracted from context",
                )

            # Look for matching open tab by domain/url
            query_lower = user_input.lower()
            for tab in open_tabs:
                if isinstance(tab, dict):
                    url = tab.get("url", "").lower()
                    if (
                        ("youtube" in query_lower and "youtube" in url)
                        or ("github" in query_lower and "github" in url)
                        or ("google" in query_lower and "google" in url)
                    ):
                        return ArgumentBuildResult(
                            success=True,
                            arguments={"tab_id": tab.get("id", 1)},
                            requires_llm=False,
                            reason=f"matched open tab {tab.get('id')}",
                        )
            return ArgumentBuildResult(
                success=False,
                arguments={},
                requires_llm=True,
                reason="tab_id ambiguous; requires reasoning",
            )

        # 2. Volume control
        elif tool_name == "volume.set":
            # Extract number from user input
            match = re.search(r"\b(\d{1,3})\b", user_input)
            if match:
                level = max(0, min(100, int(match.group(1))))
                return ArgumentBuildResult(
                    success=True,
                    arguments={"level": level},
                    requires_llm=False,
                    reason="level parsed from input",
                )
            return ArgumentBuildResult(
                success=False,
                arguments={},
                requires_llm=True,
                reason="volume level not found in query",
            )

        elif tool_name == "volume.mute":
            return ArgumentBuildResult(
                success=True,
                arguments={"mute": True},
                requires_llm=False,
                reason="deterministic mute",
            )

        # 3. System time query
        elif tool_name == "system.get_time":
            return ArgumentBuildResult(
                success=True, arguments={}, requires_llm=False, reason="no arguments required"
            )

        # 4. App focus / launch
        elif tool_name in ("app.focus", "app.launch"):
            app_name = context.get("app_name", "")
            if app_name:
                return ArgumentBuildResult(
                    success=True,
                    arguments={"name": app_name},
                    requires_llm=False,
                    reason="app_name from context",
                )
            # Simple word extraction
            words = [
                w
                for w in user_input.split()
                if w.lower() not in ("open", "launch", "start", "focus", "the", "app")
            ]
            if words:
                return ArgumentBuildResult(
                    success=True,
                    arguments={"name": words[0]},
                    requires_llm=False,
                    reason="app_name extracted from input",
                )
            return ArgumentBuildResult(
                success=False, arguments={}, requires_llm=True, reason="app name ambiguous"
            )

        # 5. Generative / Freeform / Destructive tools ALWAYS require LLM
        return ArgumentBuildResult(
            success=False,
            arguments={},
            requires_llm=True,
            reason=f"tool '{tool_name}' requires unstructured generative reasoning",
        )
