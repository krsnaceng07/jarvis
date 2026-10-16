"""jarvis.commands.agents.binding_format — human-readable binding descriptions.

OpenClaw parity: mirrors ``src/commands/agents.binding-format.ts``.

Compact single-line description of a route binding match, used in
``agents list --bindings`` and ``agents bindings`` output.
"""

from __future__ import annotations

from typing import Any


def describe_binding(binding: dict[str, Any]) -> str:
    """Render one route binding as a compact CLI line fragment.

    Mirrors ``describeBinding``.

    Example output:
        discord accountId=support
        slack accountId=default peer=direct:U123456
        discord guild=1234567890
    """
    match = binding.get("match") or {}
    parts: list[str] = []

    channel = match.get("channel") or ""
    if channel:
        parts.append(channel)

    account_id = match.get("accountId") or ""
    if account_id:
        parts.append(f"accountId={account_id}")

    peer = match.get("peer")
    if isinstance(peer, dict):
        kind = peer.get("kind", "")
        peer_id = peer.get("id", "")
        if kind or peer_id:
            parts.append(f"peer={kind}:{peer_id}")

    guild_id = match.get("guildId") or ""
    if guild_id:
        parts.append(f"guild={guild_id}")

    team_id = match.get("teamId") or ""
    if team_id:
        parts.append(f"team={team_id}")

    roles = match.get("roles")
    if isinstance(roles, list) and roles:
        parts.append(f"roles={','.join(str(r) for r in roles)}")

    comment = binding.get("comment", "")
    if not parts:
        return comment or "<empty binding>"

    result = " ".join(parts)
    if comment:
        result = f"{result}  # {comment}"
    return result


__all__ = ["describe_binding"]
