"""CUA Computer provider command execution.

OpenClaw parity: mirrors extensions/cua-computer/src/commands.ts.
Supports tiered execution via TierRouter (Tier 0 Browser -> Tier 1 UIA -> Tier 2 Overlay Real Input)
and mock mode for testing environments.
"""

from __future__ import annotations

import sys
from typing import Any

from .actions import normalize_key, normalize_modifiers


class CuaComputerProvider:
    def __init__(
        self,
        platform: str | None = None,
        driver_client: Any = None,
        router: Any = None,
        use_real_input: bool = False,
    ):
        self.platform = platform or sys.platform
        self.driver_client = driver_client
        self.use_real_input = use_real_input
        self._router = router
        self._cursor_x = 0
        self._cursor_y = 0

    @property
    def router(self) -> Any:
        if self._router is None and self.use_real_input:
            from .router import TierRouter
            self._router = TierRouter()
        return self._router

    async def execute_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.use_real_input and self.router is not None:
            return await self.router.execute_action("cua_session", action, params)

        # Mock / Fallback execution path
        if action == "cursor_position":
            return {"x": self._cursor_x, "y": self._cursor_y}

        if action == "move":
            x = int(params.get("x", 0))
            y = int(params.get("y", 0))
            self._cursor_x = x
            self._cursor_y = y
            return {"ok": True, "x": x, "y": y}

        if action in ("click", "right_click", "double_click", "triple_click", "middle_click"):
            if "x" in params and "y" in params:
                self._cursor_x = int(params["x"])
                self._cursor_y = int(params["y"])
            button = (
                "right"
                if action == "right_click"
                else "middle"
                if action == "middle_click"
                else "left"
            )
            count = 3 if action == "triple_click" else 2 if action == "double_click" else 1
            return {
                "ok": True,
                "action": action,
                "button": button,
                "count": count,
                "x": self._cursor_x,
                "y": self._cursor_y,
            }

        if action == "drag":
            path = params.get("path", [])
            if path and isinstance(path, list) and len(path) > 0:
                last = path[-1]
                if isinstance(last, dict):
                    self._cursor_x = int(last.get("x", self._cursor_x))
                    self._cursor_y = int(last.get("y", self._cursor_y))
            return {"ok": True, "action": "drag", "x": self._cursor_x, "y": self._cursor_y}

        if action == "scroll":
            delta_x = int(params.get("deltaX", 0))
            delta_y = int(params.get("deltaY", 0))
            return {"ok": True, "action": "scroll", "deltaX": delta_x, "deltaY": delta_y}

        if action == "type":
            text = str(params.get("text", ""))
            return {"ok": True, "action": "type", "text": text}

        if action == "key":
            key_val = str(params.get("key", ""))
            norm = normalize_key(key_val, self.platform)
            modifiers = normalize_modifiers(params.get("modifiers"), self.platform)
            return {"ok": True, "action": "key", "key": norm, "modifiers": modifiers}

        if action == "screenshot":
            return {"ok": True, "action": "screenshot", "format": "png", "data": "base64-png-mock"}

        raise ValueError(f"Unknown computer action: {action}")


def create_cua_computer_provider(
    platform: str | None = None,
    router: Any = None,
    use_real_input: bool = False,
) -> CuaComputerProvider:
    return CuaComputerProvider(
        platform=platform,
        router=router,
        use_real_input=use_real_input,
    )
