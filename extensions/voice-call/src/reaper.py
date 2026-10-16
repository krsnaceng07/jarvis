"""Stale telephony call session reaper for purging abandoned sessions."""

from __future__ import annotations

import logging
import time

from .config import VoiceCallConfig
from .types import CallSession

logger = logging.getLogger(__name__)


class StaleCallReaper:
    """Monitors and reaps idle or unanswered call sessions past the configured timeout threshold."""

    def __init__(self, timeout_seconds: int = 120, max_duration_seconds: int = 300) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_duration_seconds = max_duration_seconds

    def find_stale_sessions(
        self,
        sessions: dict[str, CallSession],
        current_time: float | None = None,
        max_duration_seconds: int | None = None,
    ) -> list[tuple[CallSession, str]]:
        """Identify sessions that should be reaped.

        1. If timeout_seconds > 0: Calls with NO answered_at timestamp and NOT in live
           ('speaking'/'listening') state that exceed timeout_seconds since creation.
        2. Calls with answered_at timestamp that exceed max_duration_seconds.
        """
        now = current_time or time.time()
        max_dur = (
            max_duration_seconds if max_duration_seconds is not None else self.max_duration_seconds
        )
        stale: list[tuple[CallSession, str]] = []

        for session in sessions.values():
            if not session.is_active:
                continue

            # 1. Unanswered stale reaper
            if self.timeout_seconds > 0 and session.answered_at is None:
                if session.conversation_state not in ("speaking", "listening"):
                    duration_since_created = now - session.created_at
                    if duration_since_created > self.timeout_seconds:
                        stale.append((session, "stale-unanswered-timeout"))
                        continue

            # 2. Answered max duration cap
            if session.answered_at is not None and max_dur > 0:
                call_duration = now - session.answered_at
                if call_duration > max_dur:
                    stale.append((session, "max-duration-exceeded"))

        return stale

    async def reap_stale_sessions(
        self,
        sessions: dict[str, CallSession],
        config: VoiceCallConfig,
        current_time: float | None = None,
    ) -> int:
        """Mark stale active sessions as completed/canceled and update timestamps."""
        stale_list = self.find_stale_sessions(
            sessions,
            current_time,
            max_duration_seconds=config.max_duration_seconds,
        )
        now = current_time or time.time()

        for session, reason in stale_list:
            session.status = "canceled" if "unanswered" in reason else "completed"
            session.ended_at = now
            session.metadata["reaped_reason"] = reason
            logger.info("Reaped call session %s (reason=%s)", session.id, reason)

        return len(stale_list)
