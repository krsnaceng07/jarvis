"""Profiles HTTP routes for Browser Control Server."""

from aiohttp import web


def register_profiles_routes(app: web.Application) -> None:
    """Register profiles routes to the app."""

    async def list_profiles(request: web.Request) -> web.Response:
        return web.json_response({"profiles": []})

    async def create_profile(request: web.Request) -> web.Response:
        return web.json_response({"status": "created"})

    async def delete_profile(request: web.Request) -> web.Response:
        name = request.match_info.get("name", "")
        return web.json_response({"status": "deleted", "name": name})

    app.router.add_get("/profiles", list_profiles)
    app.router.add_post("/profiles/create", create_profile)
    app.router.add_delete("/profiles/{name}", delete_profile)
