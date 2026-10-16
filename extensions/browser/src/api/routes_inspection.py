"""Inspection HTTP routes for Browser Control Server."""

from aiohttp import web

from ..browser_runtime import get_browser_runtime


def register_inspection_routes(app: web.Application) -> None:
    """Register inspection routes to the app."""

    async def get_snapshot(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        target_id = request.query.get("targetId")
        fmt = request.query.get("format", "aria")
        max_chars = int(request.query.get("maxChars", 50000))
        res = await runtime.snapshot(target_id=target_id, snapshot_format=fmt, max_chars=max_chars)
        return web.json_response(res)

    async def post_screenshot(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        data = await request.json() if request.can_read_body else {}
        target_id = data.get("targetId")
        full_page = bool(data.get("fullPage", False))
        selector = data.get("selector") or data.get("element")
        path = data.get("path")
        res = await runtime.screenshot(
            target_id=target_id, full_page=full_page, selector=selector, path=path
        )
        return web.json_response(res)

    async def get_console(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        target_id = request.query.get("targetId")
        res = await runtime.get_console(target_id=target_id)
        return web.json_response(res)

    async def get_errors(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        target_id = request.query.get("targetId")
        res = await runtime.get_errors(target_id=target_id)
        return web.json_response(res)

    async def get_requests(request: web.Request) -> web.Response:
        return web.json_response({"requests": []})

    async def get_dialogs(request: web.Request) -> web.Response:
        return web.json_response({"dialogs": []})

    async def post_pdf(request: web.Request) -> web.Response:
        return web.json_response({"pdf": "not_supported"})

    async def post_highlight(request: web.Request) -> web.Response:
        return web.json_response({"status": "highlighted"})

    app.router.add_get("/snapshot", get_snapshot)
    app.router.add_post("/screenshot", post_screenshot)
    app.router.add_get("/console", get_console)
    app.router.add_get("/errors", get_errors)
    app.router.add_get("/requests", get_requests)
    app.router.add_get("/dialogs", get_dialogs)
    app.router.add_post("/pdf", post_pdf)
    app.router.add_post("/highlight", post_highlight)
