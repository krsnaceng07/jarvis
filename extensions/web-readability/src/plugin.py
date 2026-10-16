"""Web Readability plugin entrypoint.

Registers the readability content extractor contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin
from .extractor import create_readability_web_content_extractor


@dataclass(frozen=True, slots=True)
class WebReadabilityPlugin(Plugin):
    """Web Readability infra plugin."""

    id: str = "web-readability"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Extract readable article content from local HTML web fetch responses."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Register the readability web content extractor."""
        if hasattr(ctx, "register_web_content_extractor"):
            ctx.register_web_content_extractor(create_readability_web_content_extractor())


web_readability_plugin = WebReadabilityPlugin()
entry = web_readability_plugin
