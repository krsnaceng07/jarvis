"""Dedicated Persistent JARVIS Chrome Browser Controller.

Provides high-level lifecycle, profile management, and direct action dispatch
for JARVIS's human-like, persistent Chrome engine.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from .browser_profiles import resolve_browser_config
from .browser_runtime import BrowserRuntime, get_browser_runtime
from .browser_tool import BrowserTool


DEFAULT_JARVIS_CHROME_PROFILE_DIR = Path.home() / ".jarvis" / "browser" / "chrome_profile"
DEFAULT_CDP_PORT = 9222


class JarvisChromeManager:
    """Singleton manager for the dedicated, persistent JARVIS Chrome instance."""

    _instance: Optional[JarvisChromeManager] = None

    def __init__(
        self, profile_dir: Optional[Path] = None, cdp_port: int = DEFAULT_CDP_PORT
    ) -> None:
        self.profile_dir = Path(profile_dir) if profile_dir else DEFAULT_JARVIS_CHROME_PROFILE_DIR
        self.cdp_port = int(os.environ.get("JARVIS_CHROME_CDP_PORT", str(cdp_port)))
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._tool = BrowserTool()

    @classmethod
    def get_instance(cls) -> JarvisChromeManager:
        if cls._instance is None:
            cls._instance = JarvisChromeManager()
        return cls._instance

    @property
    def tool(self) -> BrowserTool:
        return self._tool

    async def get_runtime(self) -> BrowserRuntime:
        cfg = resolve_browser_config(
            {
                "profiles": {
                    "jarvis": {
                        "driver": "jarvis",
                        "userDataDir": str(self.profile_dir),
                        "cdpPort": self.cdp_port,
                        "headless": os.environ.get("OPENCLAW_BROWSER_HEADLESS")
                        in ("1", "true", "True"),
                    }
                }
            }
        )
        return await get_browser_runtime(cfg)

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        """Execute a browser action using the canonical BrowserTool."""
        params = {"action": action, **kwargs}
        res = await self._tool.execute("jarvis_chrome_call", params)
        if hasattr(res, "details") and res.details:
            return res.details
        if hasattr(res, "content") and res.content:
            text_items = [c.text for c in res.content if hasattr(c, "text")]
            return {"ok": True, "result": "\n".join(text_items)}
        return {"ok": True}

    async def close(self) -> None:
        """Close browser runtime cleanly."""
        runtime = await self.get_runtime()
        await runtime.stop()


def get_jarvis_chrome_manager() -> JarvisChromeManager:
    """Helper to access the active JarvisChromeManager singleton."""
    return JarvisChromeManager.get_instance()
