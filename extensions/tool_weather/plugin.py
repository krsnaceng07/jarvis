"""tool_weather — Weather plugin implementation.

**Phase 1A proof consumer.** The class shape (init/manifest/tools/call)
is intentionally minimal. Phase 1C will extract the shared bits
across `tool_weather` (this) and `tool_reminder` (Phase 1B) into
`packages/plugin_sdk/`.

The host instantiates this class once at session start, calls
`init(player)` with the UI player, then dispatches tool calls via
`call(name, args)`.
"""

from __future__ import annotations

import contextlib
import webbrowser
from typing import Any
from urllib.parse import quote_plus

# Tool metadata. Kept in sync with `jarvis.plugin.json` (the manifest).
# Phase 1C will define `PluginManifest` / `ToolDecl` types in the SDK
# and these will be derived from the manifest instead of duplicated.
TOOL_NAME = "weather_report"
TOOL_DESCRIPTION = (
    "Gives the weather report for a city. Opens Google weather search in the browser."
)


class WeatherPlugin:
    """Weather tool — stateless, opens a Google search in the browser.

    Plugin contract (Phase 1A, informal — formalized in Phase 1C):
    - `id` / `kind` / `version` / `description`: identity (mirrors manifest).
    - `init(player)`: one-time setup. Player is the UI handle for log/speak.
    - `tools` property: returns the list of tool declarations for the LLM.
    - `call(name, args) -> str`: dispatches a tool call, returns the result
      (or an error message — Phase 1C will switch to a `Result` discriminated
      union; for now we follow the existing `str` return convention).
    """

    # ── Identity (mirrors `jarvis.plugin.json`) ─────────────────────
    id = "tool_weather"
    kind = "tool"
    version = "0.1.0"
    description = "Current weather and forecasts via Google search."

    def __init__(self) -> None:
        self._player: Any = None  # set by `init()`

    def init(self, player: Any) -> None:
        """One-time setup with the host's UI handle."""
        self._player = player

    @property
    def tools(self) -> list[dict[str, Any]]:
        """Tool declarations for the LLM (mirrors the manifest's `tools`)."""
        return [
            {
                "name": TOOL_NAME,
                "description": TOOL_DESCRIPTION,
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "city": {
                            "type": "STRING",
                            "description": "City name",
                        },
                        "time": {
                            "type": "STRING",
                            "description": "today, tomorrow, or a specific date",
                        },
                    },
                    "required": ["city"],
                },
            }
        ]

    def call(self, name: str, args: dict[str, Any]) -> str:
        """Dispatch a tool call by name. Returns a human-readable result."""
        if name == TOOL_NAME:
            return self._weather(args)
        return f"Unknown tool: {name}"

    # ── Tool implementations ────────────────────────────────────────
    def _weather(self, args: dict[str, Any]) -> str:
        city = (args.get("city") or "").strip()
        if not city:
            return self._speak("Sir, the city is missing for the weather report.")

        when = (args.get("time") or "today").strip()

        search_query = f"weather in {city} {when}"
        url = f"https://www.google.com/search?q={quote_plus(search_query)}"

        try:
            webbrowser.open(url)
        except Exception as e:
            return self._speak(f"Sir, I couldn't open the browser. {e}")

        return self._speak(f"Showing the weather for {city}, {when}, sir.")

    def _speak(self, message: str) -> str:
        """Log the message to the player if available. Always return it."""
        if self._player is not None:
            # Use contextlib.suppress so a broken player never crashes the tool
            # (the legacy `try/except/pass` pattern ruff flags as SIM105 + S110).
            with contextlib.suppress(Exception):
                self._player.write_log(f"JARVIS: {message}")
        return message
