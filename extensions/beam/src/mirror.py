"""Beam mirror service for periodic snapshot forwarding.

OpenClaw parity: mirrors extensions/beam/src/mirror.ts.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
import urllib.parse
import urllib.request

from .types import BeamUpload

DEFAULT_POLL_SECONDS = 30
DEFAULT_ACTIVE_WINDOW_MINUTES = 180


def parse_beam_mirror_config(
    config: dict[str, Any] | None,
) -> dict[str, Any] | None | str:
    if not isinstance(config, dict):
        return None
    plugins = config.get("plugins", {}) if isinstance(config.get("plugins"), dict) else {}
    entries = plugins.get("entries", {}) if isinstance(plugins.get("entries"), dict) else {}
    beam_entry = entries.get("beam", {}) if isinstance(entries.get("beam"), dict) else {}
    mirror = (
        beam_entry.get("config", {}).get("mirror")
        if isinstance(beam_entry.get("config"), dict)
        else None
    )

    if mirror is None:
        return None
    if not isinstance(mirror, dict):
        return "mirror config must be an object"

    endpoint = str(mirror.get("endpoint", "")).strip()
    if not endpoint:
        return "mirror.endpoint is required"

    parsed_url = urllib.parse.urlparse(endpoint)
    if parsed_url.scheme not in ("http", "https"):
        return "mirror.endpoint must be an absolute HTTP(S) URL"

    hostname = (parsed_url.hostname or "").lower()
    is_loopback = hostname in ("localhost", "127.0.0.1", "::1")
    if parsed_url.scheme == "http" and not is_loopback:
        return "mirror.endpoint must use HTTPS for remote hosts (plaintext http only allowed for loopback)"

    catalogs_raw = mirror.get("catalogs", [])
    if not isinstance(catalogs_raw, list) or not catalogs_raw:
        return "mirror.catalogs must be a non-empty list of catalog IDs"

    # Always exclude local 'beam' catalog to prevent mirror loops
    catalogs = [str(c) for c in catalogs_raw if str(c) != "beam"]
    if not catalogs:
        return "mirror.catalogs must contain catalogs other than 'beam'"

    return {
        "endpoint": endpoint,
        "token": mirror.get("token"),
        "catalogs": catalogs,
        "pollSeconds": max(10, int(mirror.get("pollSeconds") or DEFAULT_POLL_SECONDS)),
        "activeWindowMinutes": max(
            1,
            int(mirror.get("activeWindowMinutes") or DEFAULT_ACTIVE_WINDOW_MINUTES),
        ),
    }


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Do not follow redirects


class BeamMirrorService:
    id = "beam-mirror"

    def __init__(self, runtime: Any = None):
        self.runtime = runtime
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._opener = urllib.request.build_opener(NoRedirectHandler)

    async def upload_snapshot(self, endpoint: str, token: str | None, payload: BeamUpload) -> bool:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="POST")
        try:
            with self._opener.open(req, timeout=15.0) as resp:
                return resp.status in (200, 201)
        except Exception:
            return False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()


def create_beam_mirror_service(
    params: dict[str, Any] | None = None,
) -> BeamMirrorService:
    runtime = params.get("runtime") if params else None
    return BeamMirrorService(runtime=runtime)


__all__ = [
    "DEFAULT_ACTIVE_WINDOW_MINUTES",
    "DEFAULT_POLL_SECONDS",
    "BeamMirrorService",
    "create_beam_mirror_service",
    "parse_beam_mirror_config",
]
