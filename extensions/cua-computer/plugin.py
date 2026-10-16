"""CUA Computer plugin definition."""

from __future__ import annotations

from typing import Any

from .src.commands import create_cua_computer_provider


class CuaComputerPlugin:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.provider = create_cua_computer_provider()

    def register(self, api: Any) -> None:
        if hasattr(api, "register_computer_use_provider"):
            api.register_computer_use_provider(self.provider)


def get_plugin_entry() -> dict[str, Any]:
    return {
        "id": "cua-computer",
        "name": "CUA Computer",
        "plugin": CuaComputerPlugin(),
    }


cua_computer_plugin = CuaComputerPlugin()
entry = cua_computer_plugin

__all__ = ["CuaComputerPlugin", "cua_computer_plugin", "entry", "get_plugin_entry"]
