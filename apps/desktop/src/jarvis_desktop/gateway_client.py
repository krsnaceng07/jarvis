"""JARVIS Desktop HUD Gateway Client Bridge.

Connects the PyQt6 HUD to the Gateway micro-kernel on Port 7433 over WebSocket
using JSON-RPC 2.0 frames. Enables real-time progressive draft streaming,
system alerts, and agent dispatching from the HUD interface.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jarvis_gateway_protocol import GatewayWSClient

logger = logging.getLogger("jarvis.desktop.gateway_client")


class JarvisHUDGatewayBridge:
    """Full-duplex bridge between PyQt6 HUD and the Gateway micro-kernel (Port 7433)."""

    def __init__(
        self,
        url: str = "ws://127.0.0.1:7433",
        token: str | None = None,
        session_id: str = "desktop:hud:main",
        token_path: Path | None = None,
    ) -> None:
        self.url = url
        self.session_id = session_id
        self._client = GatewayWSClient(
            url=url,
            token=token,
            role="hud",
            session_id=session_id,
            token_path=token_path,
        )
        self._draft_listeners: list[Callable[[str], None]] = []
        self._alert_listeners: list[Callable[[dict[str, Any]], None]] = []

        # Wire built-in event listeners
        self._client.on_event("event.agent.draft", self._handle_agent_draft)
        self._client.on_event("event.system.alert", self._handle_system_alert)

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    async def connect(self, timeout: float = 5.0) -> dict[str, Any]:
        """Connect and authenticate with the Gateway over WebSocket."""
        res = await self._client.connect(timeout=timeout)
        # Subscribe to draft events and system alerts
        await self._client.subscribe("event.agent.draft")
        await self._client.subscribe("event.system.alert")
        logger.info("HUD connected and subscribed to Gateway events at %s", self.url)
        return res

    async def disconnect(self) -> None:
        """Disconnect cleanly from the Gateway."""
        await self._client.close()

    def on_draft(self, callback: Callable[[str], None]) -> None:
        """Register a callback for progressive streaming text deltas."""
        if callback not in self._draft_listeners:
            self._draft_listeners.append(callback)

    def on_alert(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback for system alerts."""
        if callback not in self._alert_listeners:
            self._alert_listeners.append(callback)

    async def dispatch(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        wait: bool = False,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Dispatch a user message to the agent runtime via Gateway JSON-RPC."""
        return await self._client.dispatch(
            message=message,
            session_key=self.session_id,
            context=context or {"agentId": "default", "channel": "desktop_hud"},
            wait=wait,
            timeout=timeout,
        )

    async def get_status(self) -> dict[str, Any]:
        """Query gateway status over JSON-RPC."""
        res = await self._client.call("status")
        return res if isinstance(res, dict) else {"status": res}

    async def list_claws(self) -> dict[str, Any]:
        """Query claws status over JSON-RPC."""
        res = await self._client.call("claws.list")
        return res if isinstance(res, dict) else {"claws": res}

    async def list_tools(self) -> dict[str, Any]:
        """Query tools catalog over JSON-RPC."""
        res = await self._client.call("tools.catalog")
        return res if isinstance(res, dict) else {"tools": res}

    def _handle_agent_draft(self, params: dict[str, Any]) -> None:
        """Handle incoming progressive draft preview chunk."""
        delta = str(params.get("delta") or "")
        session_key = str(params.get("sessionKey") or "")
        if delta and (not session_key or session_key == self.session_id):
            for listener in self._draft_listeners:
                try:
                    listener(delta)
                except Exception as e:
                    logger.warning("HUD draft listener error: %s", e)

    def _handle_system_alert(self, params: dict[str, Any]) -> None:
        """Handle incoming system alert."""
        for listener in self._alert_listeners:
            try:
                listener(params)
            except Exception as e:
                logger.warning("HUD alert listener error: %s", e)


def create_hud_gateway_bridge(
    url: str = "ws://127.0.0.1:7433",
    token: str | None = None,
    session_id: str = "desktop:hud:main",
) -> JarvisHUDGatewayBridge:
    """Create a HUD Gateway WebSocket bridge instance."""
    return JarvisHUDGatewayBridge(url=url, token=token, session_id=session_id)


__all__ = ["JarvisHUDGatewayBridge", "create_hud_gateway_bridge"]
