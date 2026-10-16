"""Actions HTTP routes for Browser Control Server."""

from aiohttp import web

from ..browser_runtime import get_browser_runtime


def register_actions_routes(app: web.Application) -> None:
    """Register actions routes to the app."""

    async def navigate(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        data = await request.json() if request.can_read_body else {}
        url = data.get("url", "")
        target_id = data.get("targetId")
        try:
            res = await runtime.navigate(url=url, target_id=target_id)
            return web.json_response(res)
        except Exception as e:
            return web.json_response({"error": str(e), "ok": False}, status=400)

    async def act(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        try:
            data = await request.json() if request.can_read_body else {}
            kind = data.get("kind")
            if not kind:
                return web.json_response(
                    {"error": "kind is required", "code": "ACT_KIND_REQUIRED"}, status=400
                )

            res = await runtime.act(**data)
            return web.json_response(res)
        except Exception as e:
            return web.json_response({"error": str(e), "code": "ACT_INVALID_REQUEST"}, status=400)

    app.router.add_post("/navigate", navigate)
    app.router.add_post("/act", act)
