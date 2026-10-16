"""Browser control service lifecycle for plugin-managed, in-process operation."""

import asyncio
from typing import Optional
from aiohttp import web

from .config import ResolvedBrowserConfig
from .pairing_store import PairingStore
from .api.routes_lifecycle import register_lifecycle_routes
from .api.routes_profiles import register_profiles_routes
from .api.routes_tabs import register_tabs_routes
from .api.routes_actions import register_actions_routes
from .api.routes_inspection import register_inspection_routes
from .api.routes_state import register_state_routes
from .api.routes_settings import register_settings_routes


class BrowserServerState:
    """Holds the shared in-process browser control runtime state."""

    def __init__(self, port: int, resolved: ResolvedBrowserConfig):
        self.port = port
        self.resolved = resolved
        self.server: Optional[web.AppRunner] = None


_state: Optional[BrowserServerState] = None
_lock = asyncio.Lock()


async def get_browser_control_state() -> Optional[BrowserServerState]:
    """Get the current running browser state if available."""
    async with _lock:
        return _state


async def ensure_browser_control_runtime(
    port: int, resolved: ResolvedBrowserConfig
) -> BrowserServerState:
    """Ensure the browser control runtime is running."""
    global _state
    async with _lock:
        if _state:
            return _state
        _state = BrowserServerState(port=port, resolved=resolved)
        return _state


async def start_browser_control_server(
    resolved: ResolvedBrowserConfig,
) -> Optional[BrowserServerState]:
    """Start the Browser control HTTP server."""
    global _state
    async with _lock:
        if _state and _state.server:
            return _state

        port = resolved.controlPort
        app = web.Application()

        # Simple health endpoint for now
        async def health(request: web.Request) -> web.Response:
            return web.json_response({"status": "ok"})

        async def extension_relay(request: web.Request) -> web.WebSocketResponse:
            ws = web.WebSocketResponse()
            await ws.prepare(request)

            # Simple authentication stub based on Browser Relay Authentication v2
            # Wait for auth challenge response (this is a simplified mock)
            auth_msg = await ws.receive_json()
            token = auth_msg.get("token")

            store = PairingStore()
            valid_token = store.load()

            if not token or token != valid_token:
                await ws.close(code=4003, message=b"Unauthorized")
                return ws

            await ws.send_json({"type": "auth_ok"})

            # Message loop stub
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await ws.send_json({"received": msg.data})
                elif msg.type == web.WSMsgType.ERROR:
                    print(f"Extension relay connection closed with exception {ws.exception()}")

            return ws

        app.router.add_get("/health", health)
        app.router.add_get("/browser/extension", extension_relay)

        # Register modular API routes
        register_lifecycle_routes(app)
        register_profiles_routes(app)
        register_tabs_routes(app)
        register_actions_routes(app)
        register_inspection_routes(app)
        register_state_routes(app)
        register_settings_routes(app)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()

        _state = BrowserServerState(port=port, resolved=resolved)
        _state.server = runner
        return _state


async def stop_browser_control_server() -> None:
    """Stop the Browser control HTTP server."""
    global _state
    async with _lock:
        if not _state:
            return
        if _state.server:
            await _state.server.cleanup()
        _state = None
