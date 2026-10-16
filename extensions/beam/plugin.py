"""Beam plugin definition."""

from __future__ import annotations

from typing import Any

from .src.http import create_beam_request_handler
from .src.mirror import create_beam_mirror_service
from .src.session_catalog import create_beam_session_catalog
from .src.store import create_beam_store


class BeamPlugin:
    def __init__(self):
        self.store = create_beam_store()
        self.catalog = create_beam_session_catalog(self.store)
        self.handler = create_beam_request_handler(self.store)
        self.mirror = create_beam_mirror_service()

    def register(self, api: Any) -> None:
        if hasattr(api, "register_session_catalog"):
            api.register_session_catalog(self.catalog)

        if hasattr(api, "register_http_route"):
            api.register_http_route(
                path="/api/v1/beam/sessions",
                auth="gateway",
                match="exact",
                handler=self.handler.handle_request,
            )

        if hasattr(api, "register_service"):
            api.register_service(self.mirror)


def get_plugin_entry() -> dict[str, Any]:
    return {
        "id": "beam",
        "name": "Beam",
        "plugin": BeamPlugin(),
    }


entry = get_plugin_entry()
