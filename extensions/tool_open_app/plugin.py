"""OpenAppPlugin — launches an app by user-friendly name.

Migrated from ``actions/open_app.py``. Behavior preserved exactly:
resolves a friendly name (e.g. ``\"vscode\"``) to the OS-specific
binary (e.g. ``\"code\"``) via the alias table, then delegates to
the per-OS launcher in ``runtime.py``.

Returns ``Result[str]`` (``Ok`` with a confirmation message,
``Err`` with a code on a known failure).
"""
from __future__ import annotations

import platform
from typing import Any

from jarvis_sdk import (
    Err,
    Ok,
    Result,
    ToolDecl,
    ToolParam,
    ToolPlugin,
)

from . import runtime


# ── Tool declaration (mirrors the manifest's tools[] entry) ──────────
OPEN_APP_TOOL = ToolDecl(
    name="open_app",
    description=(
        "Opens any application on the Windows computer. Use this whenever the user "
        "asks to launch, start, or open an app (e.g. 'open Chrome', 'launch VSCode')."
    ),
    parameters=[
        ToolParam(
            name="app_name",
            type="string",
            description="The name of the application to open (e.g. 'chrome', 'vscode', 'spotify').",
            required=True,
        ),
    ],
    returns="string",
    category="system",
)


class OpenAppPlugin(ToolPlugin):
    """Launches an app on the host OS.

    Plugin contract (Phase 1C, mirrors OpenClaw's ``ToolPlugin``):
    - ``id``/``kind``/``version``/``description``: identity (mirrors manifest).
    - ``tools`` property: list of ``ToolDecl`` for the LLM.
    - ``call(name, args) -> Result[str]``: dispatch + run + return ``Ok/Err``.
    """

    id = "tool_open_app"
    kind = "tool"
    version = "0.1.0"
    description = "Cross-platform app launcher (Windows / macOS / Linux)."

    def init(self, ctx: Any) -> None:
        # No persistent state.
        return

    async def shutdown(self) -> None:
        return None  # explicit no-op default; subclasses override

    @property
    def tools(self) -> list[ToolDecl]:
        return [OPEN_APP_TOOL]

    async def call(self, name: str, args: dict[str, Any]) -> Result[str]:
        if name != "open_app":
            return Err(f"Unknown tool: {name}", code="UNKNOWN_TOOL")
        return self._open(args)

    def _open(self, args: dict[str, Any]) -> Result[str]:
        """Resolve the alias for the current OS, then launch it."""
        app_name = (args.get("app_name") or "").strip()
        if not app_name:
            return Err(
                "Please specify which application to open, sir.",
                code="MISSING_ARG",
            )

        system = platform.system()
        if system not in ("Windows", "Darwin", "Linux"):
            return Err(f"Unsupported OS: {system}", code="UNSUPPORTED_OS")

        normalized = runtime.resolve_alias(app_name, system=system)
        print(f"[open_app] launching: {app_name} → {normalized} ({system})")

        if runtime.launch(normalized, system=system):
            return Ok(f"Opened {app_name} successfully, sir.")

        # Retry with the raw name in case the alias resolution was wrong.
        if normalized != app_name and runtime.launch(app_name, system=system):
            return Ok(f"Opened {app_name} successfully, sir.")

        return Err(
            f"I tried to open {app_name}, sir, but couldn't confirm it launched. "
            f"It may still be loading or might not be installed.",
            code="LAUNCH_UNCONFIRMED",
        )


__all__ = ["OPEN_APP_TOOL", "OpenAppPlugin"]
