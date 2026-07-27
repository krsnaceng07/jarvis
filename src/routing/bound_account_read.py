"""jarvis.routing.bound_account_read — account bindings from channel records.

OpenClaw parity: mirrors ``src/routing/bound-account-read.ts``.
"""

from __future__ import annotations

from typing import Any

from .agent_id import normalize_agent_id
from .binding_scope import (
    normalize_route_binding_channel_id,
    normalize_route_binding_id,
    normalize_route_binding_roles,
    resolve_normalized_route_binding_match,
    route_binding_scope_matches,
)
from .chat_type import normalize_chat_type
from .config_bindings import list_route_bindings
from .peer_kind_match import peer_kind_matches


def _resolve_normalized_bound_account_match(binding: Any) -> dict[str, Any] | None:
    """Mirrors ``resolveNormalizedBoundAccountMatch``."""
    base_match = resolve_normalized_route_binding_match(binding)
    match = binding.get("match") if isinstance(binding, dict) else None
    if not base_match or not match or not isinstance(match, dict):
        return None
    peer = match.get("peer")
    raw_peer_id = peer.get("id") if isinstance(peer, dict) else None
    peer_id = raw_peer_id.strip() if isinstance(raw_peer_id, str) else None
    peer_kind = normalize_chat_type(peer.get("kind")) if isinstance(peer, dict) else None
    return {
        **base_match,
        "peerId": peer_id or None,
        "peerKind": peer_kind,
        "guildId": normalize_route_binding_id(match.get("guildId")) or None,
        "teamId": normalize_route_binding_id(match.get("teamId")) or None,
        "roles": normalize_route_binding_roles(match.get("roles")),
    }


def _build_exact_peer_id_set(peer_id: str | None, exact_peer_id_aliases: list[str] | None) -> set[str]:
    exact_peer_ids: set[str] = set()
    trimmed = peer_id.strip() if isinstance(peer_id, str) else ""
    if trimmed:
        exact_peer_ids.add(trimmed)
    for alias in exact_peer_id_aliases or []:
        alias_trimmed = alias.strip() if isinstance(alias, str) else ""
        if alias_trimmed:
            exact_peer_ids.add(alias_trimmed)
    return exact_peer_ids


def resolve_first_bound_account_id(params: dict[str, Any]) -> str | None:
    """Mirrors ``resolveFirstBoundAccountId``.

    Params: cfg, channelId, agentId, peerId?, exactPeerIdAliases?,
    peerKind?, groupSpace?, memberRoleIds?.
    """
    normalized_channel = normalize_route_binding_channel_id(params["channelId"])
    if not normalized_channel:
        return None
    normalized_agent_id = normalize_agent_id(params["agentId"])
    raw_peer_id = params.get("peerId")
    normalized_peer_id = (
        raw_peer_id.strip() if isinstance(raw_peer_id, str) and raw_peer_id.strip() else None
    )
    exact_peer_ids = _build_exact_peer_id_set(normalized_peer_id, params.get("exactPeerIdAliases"))
    has_peer_context = len(exact_peer_ids) > 0
    normalized_peer_kind = normalize_chat_type(params.get("peerKind"))
    wildcard_peer_match: str | None = None
    channel_only_fallback: str | None = None
    for binding in list_route_bindings(params["cfg"]):
        resolved = _resolve_normalized_bound_account_match(binding)
        if (
            not resolved
            or resolved["channelId"] != normalized_channel
            or resolved["agentId"] != normalized_agent_id
        ):
            continue
        if not route_binding_scope_matches(
            resolved,
            {
                "groupSpace": params.get("groupSpace"),
                "memberRoleIds": params.get("memberRoleIds"),
            },
        ):
            continue
        if not has_peer_context:
            # Cron and other peerless callers historically used the first matching
            # agent/channel binding. Keep that fallback order unless the caller has
            # enough peer context for the stricter exact/wildcard routing below.
            return resolved["accountId"]
        if resolved["peerId"] == "*":
            # Caller has a peer. Wildcard bindings are only safe when both sides
            # declare a peer kind AND the kinds agree — a direct/* binding must
            # never win for a channel caller (or vice versa), and we'd rather fall
            # through to channel-only or the caller account than actively route to
            # the wrong identity.
            if (
                not resolved["peerKind"]
                or not normalized_peer_kind
                or not peer_kind_matches(resolved["peerKind"], normalized_peer_kind)
            ):
                continue
            if wildcard_peer_match is None:
                wildcard_peer_match = resolved["accountId"]
        elif resolved["peerId"]:
            # Exact peer id match: peer ids are channel-unique so id alone is
            # sufficient, but when both sides declare a kind they must still agree
            # (avoids a direct-kind binding matching a channel caller that happens
            # to share an id, which can occur on channels where ids are reused
            # across kinds).
            if (
                resolved["peerKind"]
                and normalized_peer_kind
                and not peer_kind_matches(resolved["peerKind"], normalized_peer_kind)
            ):
                continue
            if resolved["peerId"] in exact_peer_ids:
                return resolved["accountId"]
        else:
            if channel_only_fallback is None:
                channel_only_fallback = resolved["accountId"]
    return wildcard_peer_match if wildcard_peer_match is not None else channel_only_fallback


__all__ = ["resolve_first_bound_account_id"]
