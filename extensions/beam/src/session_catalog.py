"""Beam session catalog provider.

OpenClaw parity: mirrors extensions/beam/src/session-catalog.ts.
"""

from __future__ import annotations

from typing import Any

from .store import BeamStore
from .types import BEAM_SESSION_SHARE_ROUTE


class BeamSessionCatalog:
    id = "beam"
    label = "Beam Snapshots"
    share_route = BEAM_SESSION_SHARE_ROUTE

    def __init__(self, store: BeamStore):
        self.store = store

    async def list_sessions(
        self, limit: int = 100, prefix: str | None = None
    ) -> list[dict[str, Any]]:
        sessions = await self.store.list(limit=limit, prefix=prefix)
        return [
            {
                "id": s["beamId"],
                "source": s["source"],
                "title": s["title"],
                "updatedAt": s["updatedAt"],
                "completed": s["completed"],
                "itemCount": len(s.get("items", [])),
            }
            for s in sessions
        ]

    async def get_session(self, beam_id: str) -> dict[str, Any] | None:
        s = await self.store.get(beam_id)
        if not s:
            return None
        return dict(s)


def create_beam_session_catalog(store: BeamStore) -> BeamSessionCatalog:
    return BeamSessionCatalog(store)
