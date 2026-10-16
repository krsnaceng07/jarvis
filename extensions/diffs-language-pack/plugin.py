"""Diffs Language Pack extension plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class DiffsLanguagePackPlugin(Plugin):
    """Diffs Language Pack companion plugin."""

    id: str = "diffs-language-pack"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Additional syntax highlighting languages for the diff viewer."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Register routes or language definitions."""
        if hasattr(ctx, "register_http_route"):
            ctx.register_http_route(
                path="/plugins/diffs-language-pack",
                auth="plugin",
                match="prefix",
                handler=lambda req, res: True,
            )


diffs_language_pack_plugin = DiffsLanguagePackPlugin()
entry = diffs_language_pack_plugin
