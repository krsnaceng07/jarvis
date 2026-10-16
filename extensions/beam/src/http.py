"""Beam HTTP request handler for session snapshots.

OpenClaw parity: mirrors extensions/beam/src/http.ts.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .store import BeamStore
from .types import BEAM_MAX_BODY_BYTES, build_beam_url, parse_beam_upload


class BeamRequestHandler:
    def __init__(
        self,
        store: BeamStore,
        resolve_control_ui_base_path: Callable[[], str | None] | None = None,
    ):
        self.store = store
        self.resolve_control_ui_base_path = resolve_control_ui_base_path

    async def handle_request(
        self,
        method: str,
        body_bytes: bytes,
        client_scopes: list[str] | None = None,
        uploader_profile_id: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        scopes = client_scopes or []
        if "operator.write" not in scopes and "operator.admin" not in scopes:
            return 403, {"ok": False, "error": "operator.write is required"}

        if method != "POST":
            return 405, {"ok": False, "error": "Method Not Allowed"}

        if len(body_bytes) > BEAM_MAX_BODY_BYTES:
            return 413, {
                "ok": False,
                "error": f"request body exceeds {BEAM_MAX_BODY_BYTES} byte limit",
            }

        try:
            raw_json = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return 400, {"ok": False, "error": "invalid Beam request body"}

        ok, upload, err_msg = parse_beam_upload(raw_json)
        if not ok or upload is None:
            return 400, {"ok": False, "error": err_msg or "invalid upload"}

        stored = await self.store.put(upload, uploader_profile_id)
        base_path = (
            self.resolve_control_ui_base_path() if self.resolve_control_ui_base_path else None
        )
        url = build_beam_url(
            title=upload.get("title", ""),
            beam_id=upload["beamId"],
            base_path=base_path,
        )

        return 200, {
            "ok": True,
            "beamId": upload["beamId"],
            "url": url,
            "sharePath": url,
            "receivedAt": stored["receivedAt"],
        }


def create_beam_request_handler(
    store: BeamStore,
    resolve_control_ui_base_path: Callable[[], str | None] | None = None,
) -> BeamRequestHandler:
    return BeamRequestHandler(store, resolve_control_ui_base_path)


__all__ = ["BeamRequestHandler", "create_beam_request_handler"]
