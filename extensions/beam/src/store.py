"""Beam in-memory / state store with retention enforcement.

OpenClaw parity: mirrors extensions/beam/src/store.ts.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .types import (
    BEAM_MAX_SESSIONS,
    BEAM_RETENTION_MS,
    BeamStoredSession,
    BeamUpload,
)


class BeamStore:
    def __init__(
        self,
        max_sessions: int = BEAM_MAX_SESSIONS,
        retention_ms: int = BEAM_RETENTION_MS,
    ):
        self.max_sessions = max_sessions
        self.retention_ms = retention_ms
        self._sessions: dict[str, BeamStoredSession] = {}
        self._lock = asyncio.Lock()

    def _sweep(self, now_ms: int) -> None:
        cutoff = now_ms - self.retention_ms
        expired = [bid for bid, s in self._sessions.items() if s["receivedAt"] < cutoff]
        for bid in expired:
            del self._sessions[bid]

        if len(self._sessions) > self.max_sessions:
            sorted_sessions = sorted(self._sessions.items(), key=lambda kv: kv[1]["receivedAt"])
            excess = len(self._sessions) - self.max_sessions
            for bid, _ in sorted_sessions[:excess]:
                del self._sessions[bid]

    async def put(
        self, upload: BeamUpload, uploader_profile_id: str | None = None
    ) -> BeamStoredSession:
        async with self._lock:
            now_ms = int(time.time() * 1000)
            self._sweep(now_ms)

            beam_id = upload["beamId"]
            existing = self._sessions.get(beam_id)

            if existing:
                # 1. Reject older timestamp uploads (ignore update)
                if upload["updatedAt"] < existing["updatedAt"]:
                    return existing

                # 2. Equal timestamp: reject regression from completed to live
                if upload["updatedAt"] == existing["updatedAt"]:
                    if existing.get("completed", False) and not upload.get("completed", False):
                        return existing

                created_at = existing["createdAt"]
            else:
                created_at = now_ms

            # Accepted update: refresh retention (receivedAt) and uploader attribution
            stored: BeamStoredSession = {
                **upload,
                "createdAt": created_at,
                "receivedAt": now_ms,
                "uploaderProfileId": uploader_profile_id,
            }
            self._sessions[beam_id] = stored
            return stored

    async def get(self, beam_id: str) -> BeamStoredSession | None:
        async with self._lock:
            now_ms = int(time.time() * 1000)
            self._sweep(now_ms)
            return self._sessions.get(beam_id)

    async def delete(self, beam_id: str) -> bool:
        """Permanently and immediately delete a Beam session."""
        async with self._lock:
            if beam_id in self._sessions:
                del self._sessions[beam_id]
                return True
            return False

    async def list(self, limit: int = 100, prefix: str | None = None) -> list[BeamStoredSession]:
        async with self._lock:
            now_ms = int(time.time() * 1000)
            self._sweep(now_ms)
            results = list(self._sessions.values())
            if prefix:
                results = [s for s in results if s["beamId"].startswith(prefix)]
            results.sort(key=lambda s: s["receivedAt"], reverse=True)
            return results[:limit]


def create_beam_store(runtime: Any = None) -> BeamStore:
    return BeamStore()


__all__ = ["BeamStore", "create_beam_store"]
