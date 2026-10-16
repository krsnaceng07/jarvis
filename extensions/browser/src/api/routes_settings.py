"""Settings HTTP routes for Browser Control Server."""

from aiohttp import web


def register_settings_routes(app: web.Application) -> None:
    """Register settings routes to the app."""

    async def set_offline(request: web.Request) -> web.Response:
        return web.json_response({"status": "set"})

    async def set_headers(request: web.Request) -> web.Response:
        return web.json_response({"status": "set"})

    async def set_credentials(request: web.Request) -> web.Response:
        return web.json_response({"status": "set"})

    async def set_geolocation(request: web.Request) -> web.Response:
        return web.json_response({"status": "set"})

    async def set_media(request: web.Request) -> web.Response:
        return web.json_response({"status": "set"})

    async def set_timezone(request: web.Request) -> web.Response:
        return web.json_response({"status": "set"})

    async def set_locale(request: web.Request) -> web.Response:
        return web.json_response({"status": "set"})

    async def set_device(request: web.Request) -> web.Response:
        return web.json_response({"status": "set"})

    app.router.add_post("/set/offline", set_offline)
    app.router.add_post("/set/headers", set_headers)
    app.router.add_post("/set/credentials", set_credentials)
    app.router.add_post("/set/geolocation", set_geolocation)
    app.router.add_post("/set/media", set_media)
    app.router.add_post("/set/timezone", set_timezone)
    app.router.add_post("/set/locale", set_locale)
    app.router.add_post("/set/device", set_device)
