"""Lifecycle HTTP routes for Browser Control Server."""

from aiohttp import web

from ..browser_runtime import get_browser_runtime


def register_lifecycle_routes(app: web.Application) -> None:
    """Register lifecycle routes to the app."""

    async def status(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        return web.json_response(runtime.get_status())

    async def doctor(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        report = await runtime.doctor()
        return web.json_response(report)

    async def start(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        await runtime.ensure_browser()
        return web.json_response({"status": "started", "running": runtime.is_running})

    async def stop(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        await runtime.stop()
        return web.json_response({"status": "stopped"})

    async def reset_profile(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        await runtime.stop()
        return web.json_response({"status": "reset"})

    app.router.add_get("/", status)
    app.router.add_get("/doctor", doctor)
    app.router.add_post("/start", start)
    app.router.add_post("/stop", stop)
    app.router.add_post("/reset-profile", reset_profile)
