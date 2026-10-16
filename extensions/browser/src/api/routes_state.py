"""State HTTP routes for Browser Control Server."""

from aiohttp import web


def register_state_routes(app: web.Application) -> None:
    """Register state routes to the app."""

    async def get_cookies(request: web.Request) -> web.Response:
        return web.json_response({"cookies": []})

    async def set_cookies(request: web.Request) -> web.Response:
        return web.json_response({"status": "set"})

    async def clear_cookies(request: web.Request) -> web.Response:
        return web.json_response({"status": "cleared"})

    async def get_storage(request: web.Request) -> web.Response:
        kind = request.match_info.get("kind", "local")
        return web.json_response({"storage": {}, "kind": kind})

    async def set_storage(request: web.Request) -> web.Response:
        kind = request.match_info.get("kind", "local")
        return web.json_response({"status": "set", "kind": kind})

    async def clear_storage(request: web.Request) -> web.Response:
        kind = request.match_info.get("kind", "local")
        return web.json_response({"status": "cleared", "kind": kind})

    app.router.add_get("/cookies", get_cookies)
    app.router.add_post("/cookies/set", set_cookies)
    app.router.add_post("/cookies/clear", clear_cookies)
    app.router.add_get("/storage/{kind}", get_storage)
    app.router.add_post("/storage/{kind}/set", set_storage)
    app.router.add_post("/storage/{kind}/clear", clear_storage)
