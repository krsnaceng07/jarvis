"""Browser infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``browser`` infra
extension (436 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin, PluginApi, CliDescriptor
from .src.browser_tool import BrowserTool
from .src.cli.browser_cli import register_cli


@dataclass(frozen=True, slots=True)
class BrowserPlugin(Plugin):
    """Browser infra descriptor."""

    id: str = "browser"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Browser automation (Playwright-backed)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook."""
        return None

    def register(self, api: PluginApi) -> None:
        """Register the browser tool and CLI."""

        # We don't have a specific register_config_schema method yet in Phase 4,
        # but in actual implementation we might register the schema or just use it at runtime.

        # Register the browser tool
        if hasattr(api, "register_tool"):
            api.register_tool(BrowserTool())

        # Register CLI
        if hasattr(api, "register_cli"):
            api.register_cli(
                register_cli,
                descriptors=[
                    CliDescriptor(
                        name="browser",
                        description="Manage the OpenClaw browser automation runtime.",
                        has_subcommands=True,
                    )
                ],
            )


browser_plugin = BrowserPlugin()
entry = browser_plugin
