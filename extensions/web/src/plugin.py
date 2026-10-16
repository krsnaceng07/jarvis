"""Web plugin entrypoint."""

from typing import Any
from jarvis_sdk import Plugin

from .web_fetch_tool import web_fetch_tool


class WebPlugin(Plugin):
    """Web fetching and content extraction plugin."""

    id: str = "web"
    kind: str = "tools"
    version: str = "0.1.0"
    description: str = "Web fetching and content extraction tools."

    def init(self, ctx: Any) -> None:
        pass

    def register(self, api: Any) -> None:
        """Initialize the web plugin and register tools."""
        if hasattr(api, "register_tool"):
            api.register_tool(web_fetch_tool)


entry = WebPlugin()
