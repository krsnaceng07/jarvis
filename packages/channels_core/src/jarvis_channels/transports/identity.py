"""Channel transport identity and route synthesis for Track 3.5.

Enforces Invariant T35-05:
Inbound channel messages synthesize deterministic, server-authoritative route
triples (channel_id, external_user_id, external_thread_id) before routing to Gateway.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class ChannelRouteIdentity:
    """Deterministic server-authoritative identity triple for channel routing."""

    channel_id: str
    external_user_id: str
    external_thread_id: str = "root"
    account_id: Optional[str] = None
    guild_id: Optional[str] = None
    team_id: Optional[str] = None

    @property
    def route_triple(self) -> tuple[str, str, str]:
        """Return the authoritative (channel_id, external_user_id, external_thread_id) triple."""
        return (self.channel_id, self.external_user_id, self.external_thread_id)

    @property
    def session_key(self) -> str:
        """Deterministic session key for state and session binding."""
        thread_part = f":{self.external_thread_id}" if self.external_thread_id != "root" else ""
        return f"{self.channel_id}:{self.external_user_id}{thread_part}"


def synthesize_route_triple(
    channel_id: str,
    external_user_id: str,
    external_thread_id: str | None = None,
    account_id: str | None = None,
    guild_id: str | None = None,
    team_id: str | None = None,
) -> ChannelRouteIdentity:
    """Synthesize authoritative ChannelRouteIdentity from raw transport fields.

    Normalizes empty or missing threads to 'root'.
    """
    clean_channel = (channel_id or "unknown").strip().lower()
    clean_user = str(external_user_id or "anonymous").strip()
    clean_thread = str(external_thread_id).strip() if external_thread_id else "root"
    if not clean_thread:
        clean_thread = "root"

    return ChannelRouteIdentity(
        channel_id=clean_channel,
        external_user_id=clean_user,
        external_thread_id=clean_thread,
        account_id=account_id.strip() if account_id else None,
        guild_id=guild_id.strip() if guild_id else None,
        team_id=team_id.strip() if team_id else None,
    )


__all__ = ["ChannelRouteIdentity", "synthesize_route_triple"]
