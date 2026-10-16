"""Tabs HTTP routes for Browser Control Server."""

from aiohttp import web

from ..browser_runtime import get_browser_runtime


def register_tabs_routes(app: web.Application) -> None:
    """Register tabs routes to the app."""

    async def list_tabs(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        tabs = await runtime.list_tabs()
        return web.json_response({"tabs": tabs})

    async def open_tab(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        data = await request.json() if request.can_read_body else {}
        url = data.get("url", "about:blank")
        tab = await runtime.open_tab(url=url)
        return web.json_response({"status": "opened", "tab": tab})

    async def focus_tab(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        data = await request.json() if request.can_read_body else {}
        target_id = data.get("targetId", "")
        res = await runtime.focus_tab(target_id=target_id)
        return web.json_response(res)

    async def close_tab(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        target_id = request.match_info.get("targetId", "")
        res = await runtime.close_tab(target_id=target_id)
        return web.json_response(res)

    async def tab_action(request: web.Request) -> web.Response:
        runtime = await get_browser_runtime()
        data = await request.json() if request.can_read_body else {}
        action = data.get("action", "")
        target_id = data.get("targetId")
        if action == "new":
            tab = await runtime.open_tab(url=data.get("url", "about:blank"))
            return web.json_response({"status": "created", "tab": tab})
        elif action == "close" and target_id:
            res = await runtime.close_tab(target_id=target_id)
            return web.json_response(res)
        elif action == "select" and target_id:
            res = await runtime.focus_tab(target_id=target_id)
            return web.json_response(res)
        return web.json_response({"status": "action_executed"})

    app.router.add_get("/tabs", list_tabs)
    app.router.add_post("/tabs/open", open_tab)
    app.router.add_post("/tabs/focus", focus_tab)
    app.router.add_delete("/tabs/{targetId}", close_tab)
    app.router.add_post("/tabs/action", tab_action)
