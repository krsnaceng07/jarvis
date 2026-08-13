"""Channel send target resolver — mirrors OpenClaw ``src/channels/targets.ts``."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChannelTarget:
    channel_id: str
    target_id: str
    thread_id: str | None = None
    account_id: str | None = None


def resolve_send_target(
    channel_id: str,
    target_id: str,
    thread_id: str | None = None,
    account_id: str | None = None,
) -> ChannelTarget:
    """Create normalized ChannelTarget."""
    return ChannelTarget(
        channel_id=channel_id.strip().lower(),
        target_id=str(target_id).strip(),
        thread_id=str(thread_id).strip() if thread_id else None,
        account_id=str(account_id).strip() if account_id else None,
    )


__all__ = ["ChannelTarget", "resolve_send_target"]
