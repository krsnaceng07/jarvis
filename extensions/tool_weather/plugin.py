"""tool_weather — Weather plugin implementation.

**Phase 1A proof consumer.** The class shape (init/manifest/tools/call)
is intentionally minimal. Phase 1C will extract the shared bits
across ``tool_weather`` (this) and ``tool_reminder`` (PR 1B) into
``packages/plugin_sdk/`` and harden the contract.

The host instantiates this class once at session start, calls
``init(player)`` with the UI player, then dispatches tool calls via
``call(name, args)``.
"""

from __future__ import annotations

import contextlib
import webbrowser
from typing import Any
from urllib.parse import quote_plus

from jarvis_sdk import Err, Ok, Result, ToolDecl, ToolParam, ToolPlugin

# ── Tool declaration (mirrors the manifest's tools[] entry) ──────────
WEATHER_TOOL = ToolDecl(
    name="weather_report",
    description=(
        "Gives the weather report for a city. Opens Google weather search in the browser."
    ),
    parameters=[
        ToolParam(
            name="city",
            type="string",
            description="City name",
            required=True,
        ),
        ToolParam(
            name="time",
            type="string",
            description="today, tomorrow, or a specific date",
            required=False,
        ),
    ],
    returns="string",
    category="information",
)


class WeatherPlugin(ToolPlugin):
    """Weather tool — stateless, opens a Google search in the browser.

    Plugin contract (PR 1B, formalized in Phase 1C):
    - ``id``/``kind``/``version``/``description``: identity (mirrors manifest).
    - ``init(ctx)``: one-time setup. Player is the UI handle for log/speak.
    - ``tools`` property: returns the list of ``ToolDecl`` for the LLM.
    - ``call(name, args) -> Result[str]``: dispatches a tool call and
      returns ``Ok(value)`` on success or ``Err(message, code)`` on
      a known failure. (PR 1A returned ``str``; PR 1B upgrades to
      the SDK's ``Result`` discriminated union.)
    """

    # ── Identity (mirrors `openclaw.plugin.json`) ───────────────────
    id = "tool_weather"
    kind = "tool"
    version = "0.1.0"
    description = "Current weather and forecasts via Google search."

    def __init__(self) -> None:
        self._player: Any = None  # set by `init()`

    def init(self, ctx: Any) -> None:
        """One-time setup with the host's UI handle.

        The base ``Plugin`` class passes a ``PluginContext``; for the
        weather plugin we only need the UI player for log/speak, so we
        accept the full context and just keep a reference. (Phase 1C
        will switch to ``ctx.player``.)
        """
        # Today the host calls ``init(self._player)`` for the legacy
        # JarvisUI handle. Once ``PluginContext`` carries the player
        # itself, this becomes ``self._player = ctx.player``.
        self._player = ctx

    # ── Tool surface ─────────────────────────────────────────────────
    @property
    def tools(self) -> list[ToolDecl]:
        """Tool declarations for the LLM (mirrors the manifest's `tools`)."""
        return [WEATHER_TOOL]

    async def call(self, name: str, args: dict[str, Any]) -> Result[str]:
        """Dispatch a tool call by name. Returns ``Ok``/``Err``."""
        if name == WEATHER_TOOL.name:
            return self._weather(args)
        return Err(f"Unknown tool: {name}", code="UNKNOWN_TOOL")

    # ── Tool implementations ────────────────────────────────────────
    def _weather(self, args: dict[str, Any]) -> Result[str]:
        city = (args.get("city") or "").strip()
        if not city:
            return Err("Sir, the city is missing for the weather report.", code="MISSING_ARG")

        when = (args.get("time") or "today").strip()

        search_query = f"weather in {city} {when}"
        url = f"https://www.google.com/search?q={quote_plus(search_query)}"

        try:
            webbrowser.open(url)
        except Exception as e:
            return Err(f"Sir, I couldn't open the browser. {e}", code="BROWSER_ERROR")

        return Ok(self._speak(f"Showing the weather for {city}, {when}, sir."))

    def _speak(self, message: str) -> str:
        """Log the message to the player if available. Always return it."""
        if self._player is not None:
            # Use contextlib.suppress so a broken player never crashes the tool
            # (the legacy `try/except/pass` pattern ruff flags as SIM105 + S110).
            with contextlib.suppress(Exception):
                self._player.write_log(f"JARVIS: {message}")
        return message
