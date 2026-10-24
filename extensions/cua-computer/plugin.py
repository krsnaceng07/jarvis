"""CUA Computer plugin definition."""

from __future__ import annotations

import json
import sys
from typing import Any

from jarvis_sdk import Err, Ok, ToolDecl, ToolParam, ToolPlugin

from . import doctor as doctor_module
from .src.commands import create_cua_computer_provider


class CuaComputerPlugin(ToolPlugin):
    id = "cua-computer"
    kind = "tool"
    version = "0.1.0"
    description = "Grounded native computer input routed through the CUA safety arbiter."

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.provider = create_cua_computer_provider(use_real_input=sys.platform == "win32")
        self.context: Any = None

    def init(self, ctx: Any) -> None:
        self.context = ctx

    @property
    def tools(self) -> list[ToolDecl]:
        return [
            ToolDecl(
                name="computer",
                description=(
                    "Perform a grounded Windows desktop input action through JARVIS's "
                    "exclusive input lease and safety policy."
                ),
                parameters=[
                    ToolParam(
                        name="action",
                        type="string",
                        description="Input action to perform.",
                        required=True,
                        enum=[
                            "click",
                            "right_click",
                            "double_click",
                            "move",
                            "type",
                            "key",
                            "scroll",
                            "drag",
                            "screenshot",
                            "cursor_position",
                        ],
                    ),
                    ToolParam(name="x", type="integer", description="Target X coordinate."),
                    ToolParam(name="y", type="integer", description="Target Y coordinate."),
                    ToolParam(name="text", type="string", description="Text to type."),
                    ToolParam(name="key", type="string", description="Key to press."),
                    ToolParam(
                        name="modifiers",
                        type="array",
                        description="Optional keyboard modifiers.",
                    ),
                    ToolParam(name="deltaX", type="integer", description="Horizontal scroll."),
                    ToolParam(name="deltaY", type="integer", description="Vertical scroll."),
                ],
            )
        ]

    async def call(self, name: str, args: dict[str, Any]) -> Any:
        if name != "computer":
            return Err(f"Unknown CUA tool: {name}", code="UNKNOWN_TOOL")
        if sys.platform != "win32":
            return Err(
                "Native CUA input is currently supported only on Windows.",
                code="UNSUPPORTED_PLATFORM",
            )

        action = str(args.get("action") or "").strip().lower()
        aliases = {
            "move_cursor": "move",
            "press_key": "key",
            "hotkey": "key",
            "scroll_at": "scroll",
            "double_click_coordinate": "double_click",
            "context_click": "right_click",
        }
        action = aliases.get(action, action)
        result = await self.provider.execute_action(action, args)
        if result.get("ok") is not True:
            return Err(
                str(result.get("error") or "Computer action failed."),
                code=str(result.get("code") or "ACTION_FAILED"),
            )
        return Ok(json.dumps(result, ensure_ascii=False))

    def register(self, api: Any) -> None:
        api.register_tool(self, {"names": [tool.name for tool in self.tools]})

        # Doctor contract — verifies desktop access and hook readiness
        if hasattr(api, "register_doctor_contract"):
            api.register_doctor_contract(
                {
                    "id": "cua-computer.input_backend",
                    "version": 1,
                    "detect_label": "Windows Native Input Synthesis",
                    "detect": doctor_module.diagnose_computer_input,
                    "apply": None,
                }
            )


def get_plugin_entry() -> dict[str, Any]:
    return {"id": "cua-computer", "name": "CUA Computer", "plugin": CuaComputerPlugin()}


cua_computer_plugin = CuaComputerPlugin()
entry = cua_computer_plugin

__all__ = ["CuaComputerPlugin", "cua_computer_plugin", "entry", "get_plugin_entry"]
