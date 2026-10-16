"""Geolocation plugin definition."""

from __future__ import annotations

import os
from typing import Any

from .src.config import resolve_geolocation_settings
from .src.database_store import create_geolocation_database_store
from .src.lookup_route import create_geolocation_lookup_handler


class GeolocationPlugin:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def register(self, api: Any) -> None:
        cfg = getattr(api, "plugin_config", None) or getattr(api, "config", None) or self.config
        settings = resolve_geolocation_settings(cfg)
        state_dir = os.environ.get("JARVIS_STATE_DIR", os.path.expanduser("~/.jarvis/state"))
        store = create_geolocation_database_store(
            state_dir=state_dir,
            settings=settings,
            logger=getattr(api, "logger", None),
        )
        handler = create_geolocation_lookup_handler(
            load_database=store.load,
            settings=settings,
            logger=getattr(api, "logger", None),
        )

        if hasattr(api, "register_http_route"):
            api.register_http_route(
                path="/plugins/geolocation",
                auth="gateway",
                match="prefix",
                handler=handler.handle_request,
            )


def get_plugin_entry() -> dict[str, Any]:
    return {
        "id": "geolocation",
        "name": "Geolocation",
        "plugin": GeolocationPlugin(),
    }


geolocation_plugin = GeolocationPlugin()
entry = geolocation_plugin

__all__ = ["GeolocationPlugin", "geolocation_plugin", "entry", "get_plugin_entry"]
