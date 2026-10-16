"""Visitor access plugin entry point."""

from __future__ import annotations

from typing import Any

from .src.cloudflare import VisitorPolicyClient
from .src.config import resolve_visitor_access_config
from .src.errors import visitor_error_text
from .src.runtime import VisitorRuntime, visitor_runtime_store
from .src.tools import create_visitor_tools
from .src.visitors import VisitorAccessService


class VisitorAccessPlugin:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def register(self, api: Any) -> None:
        if hasattr(api, "register_tool"):
            for tool in create_visitor_tools(api):
                api.register_tool(tool)

        if not self.config or not self.config.get("apiToken"):
            return

        resolved_config = resolve_visitor_access_config(self.config)
        client = VisitorPolicyClient(resolved_config)
        service = VisitorAccessService(
            config=resolved_config,
            policy_client=client,
            logger=getattr(api, "logger", None),
        )
        runtime = VisitorRuntime(
            service=service,
            error_text_fn=lambda e: visitor_error_text(e, resolved_config["apiToken"]),
        )
        visitor_runtime_store.set_runtime(runtime)


def get_plugin_entry() -> dict[str, Any]:
    return {
        "id": "visitor-access",
        "name": "Visitor Access",
        "plugin": VisitorAccessPlugin(),
    }


visitor_access_plugin = VisitorAccessPlugin()
entry = visitor_access_plugin

__all__ = ["VisitorAccessPlugin", "visitor_access_plugin", "entry", "get_plugin_entry"]
