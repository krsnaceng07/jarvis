"""jarvis.routing.resolve_route — tiered agent route resolution.

OpenClaw parity: mirrors ``src/routing/resolve-route.ts`` exactly:
same tier order (exact peer → parent-peer → wildcard peer →
guild+roles → guild → team → account → channel → default), same
evaluated-bindings index buckets, same ref-identity-invalidated
caches (WeakMap-per-cfg → id(cfg)-keyed dict with ref checks), same
cache-size clamps (2000 evaluated-binding keys / 4000 resolved-route
keys), and the same cache-disable conditions (verbose logging or
``session.identityLinks``).

The ``should_log_verbose`` / ``log_debug`` hooks default to off /
stderr; the host wires them to the real logger (Phase 5.15+).
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from jarvis_normalization_core.string_coerce import normalize_lowercase_string_or_empty

from .agent_scope import resolve_default_agent_id
from .binding_scope import (
    normalize_route_binding_id,
    normalize_route_binding_roles,
    route_binding_scope_matches,
)
from .chat_type import normalize_chat_type
from .peer_kind_match import peer_kind_matches
from .session_key import (
    DEFAULT_ACCOUNT_ID,
    DEFAULT_MAIN_KEY,
    build_agent_main_session_key,
    build_agent_peer_session_key,
    normalize_account_id,
    normalize_agent_id,
    sanitize_agent_id,
)

# ---------------------------------------------------------------------------
# Logger seams (mirror ../globals.js shouldLogVerbose + ../logger.js logDebug)
# ---------------------------------------------------------------------------

should_log_verbose: Callable[[], bool] = lambda: False  # noqa: E731


def log_debug(message: str) -> None:
    print(message, file=sys.stderr)


def set_routing_log_hooks(
    verbose: Callable[[], bool] | None = None,
    debug: Callable[[str], None] | None = None,
) -> None:
    """Wire the verbose/debug seams to the host logger (test/host seam)."""
    global should_log_verbose, log_debug
    if verbose is not None:
        should_log_verbose = verbose
    if debug is not None:
        log_debug = debug


# ---------------------------------------------------------------------------
# Route policy helpers
# ---------------------------------------------------------------------------


def derive_last_route_policy(params: dict[str, Any]) -> str:
    """Mirrors ``deriveLastRoutePolicy``: "main" when the session key IS the
    main key, else "session"."""
    return "main" if params["sessionKey"] == params["mainSessionKey"] else "session"


def resolve_inbound_last_route_session_key(params: dict[str, Any]) -> str:
    """Mirrors ``resolveInboundLastRouteSessionKey``."""
    route = params["route"]
    return route["mainSessionKey"] if route["lastRoutePolicy"] == "main" else params["sessionKey"]


def _normalize_token(value: object) -> str:
    return normalize_lowercase_string_or_empty(value)


def _normalize_id(value: object) -> str:
    return normalize_route_binding_id(value)


def build_agent_session_key(params: dict[str, Any]) -> str:
    """Mirrors ``buildAgentSessionKey``.

    Params: agentId, mainKey?, channel, accountId?, peer?, dmScope?,
    identityLinks?.
    """
    channel = _normalize_token(params.get("channel")) or "unknown"
    peer = params.get("peer")
    main_key = params.get("mainKey")
    return build_agent_peer_session_key(
        {
            "agentId": params["agentId"],
            "mainKey": main_key if main_key is not None else DEFAULT_MAIN_KEY,
            "channel": channel,
            "accountId": params.get("accountId"),
            "peerKind": (peer.get("kind") if peer else None) or "direct",
            "peerId": (_normalize_id(peer.get("id")) or "unknown") if peer else None,
            "dmScope": params.get("dmScope"),
            "identityLinks": params.get("identityLinks"),
        }
    )


# ---------------------------------------------------------------------------
# Agent lookup cache (WeakMap-per-cfg → id(cfg)-keyed, agents-ref checked)
# ---------------------------------------------------------------------------


def _list_agents(cfg: dict[str, Any]) -> list[Any]:
    agents = cfg.get("agents")
    agent_list = agents.get("list") if isinstance(agents, dict) else None
    return agent_list if isinstance(agent_list, list) else []


# id(cfg) -> {"agentsRef", "byNormalizedId", "fallbackDefaultAgentId"}
_agent_lookup_cache_by_cfg: dict[int, dict[str, Any]] = {}


def _resolve_agent_lookup_cache(cfg: dict[str, Any]) -> dict[str, Any]:
    agents_ref = cfg.get("agents")
    existing = _agent_lookup_cache_by_cfg.get(id(cfg))
    if existing is not None and existing["agentsRef"] is agents_ref:
        return existing

    by_normalized_id: dict[str, str] = {}
    for agent in _list_agents(cfg):
        raw = agent.get("id") if isinstance(agent, dict) else None
        raw_id = raw.strip() if isinstance(raw, str) else ""
        if not raw_id:
            continue
        by_normalized_id[normalize_agent_id(raw_id)] = sanitize_agent_id(raw_id)
    next_cache = {
        "agentsRef": agents_ref,
        "byNormalizedId": by_normalized_id,
        "fallbackDefaultAgentId": sanitize_agent_id(resolve_default_agent_id(cfg)),
    }
    _agent_lookup_cache_by_cfg[id(cfg)] = next_cache
    return next_cache


def pick_first_existing_agent_id(cfg: dict[str, Any], agent_id: str) -> str:
    """Mirrors ``pickFirstExistingAgentId``."""
    lookup = _resolve_agent_lookup_cache(cfg)
    trimmed = (agent_id or "").strip()
    if not trimmed:
        return lookup["fallbackDefaultAgentId"]
    normalized = normalize_agent_id(trimmed)
    if len(lookup["byNormalizedId"]) == 0:
        return sanitize_agent_id(trimmed)
    resolved = lookup["byNormalizedId"].get(normalized)
    if resolved:
        return resolved
    return lookup["fallbackDefaultAgentId"]


# ---------------------------------------------------------------------------
# Binding evaluation + indexing
# ---------------------------------------------------------------------------
# NormalizedPeerConstraint: {"state": "none"} | {"state": "invalid"}
#   | {"state": "wildcard-kind", "kind"} | {"state": "valid", "kind", "id"}
# EvaluatedBinding: {"binding", "match", "order"}

_MAX_EVALUATED_BINDINGS_CACHE_KEYS = 2000
_MAX_RESOLVED_ROUTE_CACHE_KEYS = 4000

# id(cfg) -> evaluated-bindings cache dict
_evaluated_bindings_cache_by_cfg: dict[int, dict[str, Any]] = {}
# id(cfg) -> resolved-route cache dict
_resolved_route_cache_by_cfg: dict[int, dict[str, Any]] = {}


def _resolve_account_pattern_key(account_pattern: str) -> str:
    if not account_pattern.strip():
        return DEFAULT_ACCOUNT_ID
    return normalize_account_id(account_pattern)


def _build_evaluated_bindings_by_channel(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    # Import late so tests can monkeypatch src.routing.bindings.list_bindings
    # (mirrors the TS module-namespace spy in resolve-route.test.ts #36915).
    from . import bindings as bindings_module

    by_channel: dict[str, dict[str, Any]] = {}
    order = 0
    for binding in bindings_module.list_bindings(cfg):
        if not binding or not isinstance(binding, dict):
            continue
        raw_match = binding.get("match")
        channel = _normalize_token(raw_match.get("channel") if isinstance(raw_match, dict) else None)
        if not channel:
            continue
        match = _normalize_binding_match(raw_match if isinstance(raw_match, dict) else None)
        evaluated = {"binding": binding, "match": match, "order": order}
        order += 1
        bucket = by_channel.get(channel)
        if bucket is None:
            bucket = {"byAccount": {}, "byAnyAccount": []}
            by_channel[channel] = bucket
        if match["accountPattern"] == "*":
            bucket["byAnyAccount"].append(evaluated)
            continue
        account_key = _resolve_account_pattern_key(match["accountPattern"])
        existing = bucket["byAccount"].get(account_key)
        if existing is not None:
            existing.append(evaluated)
            continue
        bucket["byAccount"][account_key] = [evaluated]
    return by_channel


def _merge_evaluated_bindings_in_source_order(
    account_scoped: list[dict[str, Any]], any_account: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if len(account_scoped) == 0:
        return any_account
    if len(any_account) == 0:
        return account_scoped
    merged: list[dict[str, Any]] = []
    account_idx = 0
    any_idx = 0
    while account_idx < len(account_scoped) and any_idx < len(any_account):
        account_binding = account_scoped[account_idx]
        any_binding = any_account[any_idx]
        if account_binding["order"] <= any_binding["order"]:
            merged.append(account_binding)
            account_idx += 1
            continue
        merged.append(any_binding)
        any_idx += 1
    if account_idx < len(account_scoped):
        merged.extend(account_scoped[account_idx:])
    if any_idx < len(any_account):
        merged.extend(any_account[any_idx:])
    return merged


def _push_to_index_map(
    mapping: dict[str, list[dict[str, Any]]], key: str | None, binding: dict[str, Any]
) -> None:
    if not key:
        return
    existing = mapping.get(key)
    if existing is not None:
        existing.append(binding)
        return
    mapping[key] = [binding]


def _peer_lookup_keys(kind: str, peer_id: str) -> list[str]:
    if kind == "group":
        return [f"group:{peer_id}", f"channel:{peer_id}"]
    if kind == "channel":
        return [f"channel:{peer_id}", f"group:{peer_id}"]
    return [f"{kind}:{peer_id}"]


def _collect_peer_indexed_bindings(
    index: dict[str, Any], peer: dict[str, Any] | None
) -> list[dict[str, Any]]:
    if not peer:
        return []
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for key in _peer_lookup_keys(peer["kind"], peer["id"]):
        matches = index["byPeer"].get(key)
        if not matches:
            continue
        for match in matches:
            if id(match) in seen:
                continue
            seen.add(id(match))
            out.append(match)
    return out


def _build_evaluated_bindings_index(bindings: list[dict[str, Any]]) -> dict[str, Any]:
    by_peer: dict[str, list[dict[str, Any]]] = {}
    by_peer_wildcard: list[dict[str, Any]] = []
    by_guild_with_roles: dict[str, list[dict[str, Any]]] = {}
    by_guild: dict[str, list[dict[str, Any]]] = {}
    by_team: dict[str, list[dict[str, Any]]] = {}
    by_account: list[dict[str, Any]] = []
    by_channel: list[dict[str, Any]] = []

    for binding in bindings:
        match = binding["match"]
        peer = match["peer"]
        if peer["state"] == "valid":
            for key in _peer_lookup_keys(peer["kind"], peer["id"]):
                _push_to_index_map(by_peer, key, binding)
            continue
        if peer["state"] == "wildcard-kind":
            by_peer_wildcard.append(binding)
            continue
        if match["guildId"] and match["roles"]:
            _push_to_index_map(by_guild_with_roles, match["guildId"], binding)
            continue
        if match["guildId"] and not match["roles"]:
            _push_to_index_map(by_guild, match["guildId"], binding)
            continue
        if match["teamId"]:
            _push_to_index_map(by_team, match["teamId"], binding)
            continue
        if match["accountPattern"] != "*":
            by_account.append(binding)
            continue
        by_channel.append(binding)

    return {
        "byPeer": by_peer,
        "byPeerWildcard": by_peer_wildcard,
        "byGuildWithRoles": by_guild_with_roles,
        "byGuild": by_guild,
        "byTeam": by_team,
        "byAccount": by_account,
        "byChannel": by_channel,
    }


def _get_evaluated_bindings_for_channel_account(
    cfg: dict[str, Any], channel: str, account_id: str
) -> list[dict[str, Any]]:
    bindings_ref = cfg.get("bindings")
    existing = _evaluated_bindings_cache_by_cfg.get(id(cfg))
    if existing is not None and existing["bindingsRef"] is bindings_ref:
        cache = existing
    else:
        cache = {
            "bindingsRef": bindings_ref,
            "byChannel": _build_evaluated_bindings_by_channel(cfg),
            "byChannelAccount": {},
            "byChannelAccountIndex": {},
        }
    if cache is not existing:
        _evaluated_bindings_cache_by_cfg[id(cfg)] = cache

    cache_key = f"{channel}\t{account_id}"
    hit = cache["byChannelAccount"].get(cache_key)
    if hit is not None:
        return hit

    channel_bindings = cache["byChannel"].get(channel)
    account_scoped = (
        channel_bindings["byAccount"].get(account_id, []) if channel_bindings else []
    )
    any_account = channel_bindings["byAnyAccount"] if channel_bindings else []
    evaluated = _merge_evaluated_bindings_in_source_order(account_scoped, any_account)

    cache["byChannelAccount"][cache_key] = evaluated
    cache["byChannelAccountIndex"][cache_key] = _build_evaluated_bindings_index(evaluated)
    if len(cache["byChannelAccount"]) > _MAX_EVALUATED_BINDINGS_CACHE_KEYS:
        cache["byChannelAccount"].clear()
        cache["byChannelAccountIndex"].clear()
        cache["byChannelAccount"][cache_key] = evaluated
        cache["byChannelAccountIndex"][cache_key] = _build_evaluated_bindings_index(evaluated)

    return evaluated


def _get_evaluated_binding_index_for_channel_account(
    cfg: dict[str, Any], channel: str, account_id: str
) -> dict[str, Any]:
    bindings = _get_evaluated_bindings_for_channel_account(cfg, channel, account_id)
    existing = _evaluated_bindings_cache_by_cfg.get(id(cfg))
    cache_key = f"{channel}\t{account_id}"
    indexed = existing["byChannelAccountIndex"].get(cache_key) if existing else None
    if indexed is not None:
        return indexed
    built = _build_evaluated_bindings_index(bindings)
    if existing is not None:
        existing["byChannelAccountIndex"][cache_key] = built
    return built


def _normalize_peer_constraint(peer: dict[str, Any] | None) -> dict[str, Any]:
    if not peer:
        return {"state": "none"}
    kind = normalize_chat_type(peer.get("kind"))
    peer_id = _normalize_id(peer.get("id"))
    if not kind or not peer_id:
        return {"state": "invalid"}
    if peer_id == "*":
        return {"state": "wildcard-kind", "kind": kind}
    return {"state": "valid", "kind": kind, "id": peer_id}


def _normalize_binding_match(match: dict[str, Any] | None) -> dict[str, Any]:
    raw_roles = match.get("roles") if match else None
    raw_account = match.get("accountId") if match else None
    return {
        "accountPattern": (raw_account if isinstance(raw_account, str) else "").strip(),
        "peer": _normalize_peer_constraint(match.get("peer") if match else None),
        "guildId": _normalize_id(match.get("guildId") if match else None) or None,
        "teamId": _normalize_id(match.get("teamId") if match else None) or None,
        "roles": normalize_route_binding_roles(raw_roles),
    }


def _resolve_route_cache_for_config(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    existing = _resolved_route_cache_by_cfg.get(id(cfg))
    if (
        existing is not None
        and existing["bindingsRef"] is cfg.get("bindings")
        and existing["agentsRef"] is cfg.get("agents")
        and existing["sessionRef"] is cfg.get("session")
    ):
        return existing["byKey"]
    by_key: dict[str, dict[str, Any]] = {}
    _resolved_route_cache_by_cfg[id(cfg)] = {
        "bindingsRef": cfg.get("bindings"),
        "agentsRef": cfg.get("agents"),
        "sessionRef": cfg.get("session"),
        "byKey": by_key,
    }
    return by_key


def _format_route_cache_peer(peer: dict[str, Any] | None) -> str:
    if not peer or not peer.get("id"):
        return "-"
    return f"{peer['kind']}:{peer['id']}"


def _format_role_ids_cache_key(role_ids: list[str]) -> str:
    count = len(role_ids)
    if count == 0:
        return "-"
    if count == 1:
        return role_ids[0] if role_ids[0] is not None else "-"
    if count == 2:
        first = role_ids[0] or ""
        second = role_ids[1] or ""
        return f"{first},{second}" if first <= second else f"{second},{first}"
    return ",".join(sorted(role_ids))


def _build_resolved_route_cache_key(params: dict[str, Any]) -> str:
    return (
        f"{params['channel']}\t{params['accountId']}\t"
        f"{_format_route_cache_peer(params['peer'])}\t"
        f"{_format_route_cache_peer(params['parentPeer'])}\t"
        f"{params['guildId'] or '-'}\t{params['teamId'] or '-'}\t"
        f"{_format_role_ids_cache_key(params['memberRoleIds'])}\t{params['dmScope']}"
    )


def _has_guild_constraint(match: dict[str, Any]) -> bool:
    return bool(match["guildId"])


def _has_team_constraint(match: dict[str, Any]) -> bool:
    return bool(match["teamId"])


def _has_roles_constraint(match: dict[str, Any]) -> bool:
    return bool(match["roles"])


def _matches_binding_scope(match: dict[str, Any], scope: dict[str, Any]) -> bool:
    """Mirrors ``matchesBindingScope``."""
    peer_constraint = match["peer"]
    scope_peer = scope.get("peer")
    if peer_constraint["state"] == "invalid":
        return False
    if peer_constraint["state"] == "valid":
        if (
            not scope_peer
            or not peer_kind_matches(peer_constraint["kind"], scope_peer["kind"])
            or scope_peer["id"] != peer_constraint["id"]
        ):
            return False
    if peer_constraint["state"] == "wildcard-kind":
        if not scope_peer or not peer_kind_matches(peer_constraint["kind"], scope_peer["kind"]):
            return False
    return route_binding_scope_matches(match, scope)


# ---------------------------------------------------------------------------
# resolveAgentRoute
# ---------------------------------------------------------------------------


def resolve_agent_route(input: dict[str, Any]) -> dict[str, Any]:
    """Mirrors ``resolveAgentRoute``.

    Input: cfg, channel, accountId?, peer?, dmScope?, parentPeer?,
    guildId?, teamId?, memberRoleIds?. Returns a ResolvedAgentRoute dict
    with agentId, channel, accountId, dmScope, sessionKey,
    mainSessionKey, lastRoutePolicy, matchedBy.
    """
    cfg = input["cfg"]
    session_cfg = cfg.get("session") if isinstance(cfg.get("session"), dict) else None
    channel = _normalize_token(input.get("channel"))
    account_id = normalize_account_id(input.get("accountId"))
    raw_peer = input.get("peer")
    peer = (
        {
            "kind": normalize_chat_type(raw_peer.get("kind")) or raw_peer.get("kind"),
            "id": _normalize_id(raw_peer.get("id")),
        }
        if raw_peer
        else None
    )
    guild_id = _normalize_id(input.get("guildId"))
    team_id = _normalize_id(input.get("teamId"))
    member_role_ids = input.get("memberRoleIds") or []
    member_role_id_set = set(member_role_ids)
    dm_scope = (
        input.get("dmScope")
        or (session_cfg.get("dmScope") if session_cfg else None)
        or "main"
    )
    identity_links = session_cfg.get("identityLinks") if session_cfg else None
    should_log_debug = should_log_verbose()
    raw_parent_peer = input.get("parentPeer")
    parent_peer = (
        {
            "kind": normalize_chat_type(raw_parent_peer.get("kind")) or raw_parent_peer.get("kind"),
            "id": _normalize_id(raw_parent_peer.get("id")),
        }
        if raw_parent_peer
        else None
    )

    route_cache = (
        _resolve_route_cache_for_config(cfg)
        if not should_log_debug and not identity_links
        else None
    )
    route_cache_key = (
        _build_resolved_route_cache_key(
            {
                "channel": channel,
                "accountId": account_id,
                "peer": peer,
                "parentPeer": parent_peer,
                "guildId": guild_id,
                "teamId": team_id,
                "memberRoleIds": member_role_ids,
                "dmScope": dm_scope,
            }
        )
        if route_cache is not None
        else ""
    )
    if route_cache is not None and route_cache_key:
        cached_route = route_cache.get(route_cache_key)
        if cached_route is not None:
            return {**cached_route}

    bindings = _get_evaluated_bindings_for_channel_account(cfg, channel, account_id)
    bindings_index = _get_evaluated_binding_index_for_channel_account(cfg, channel, account_id)

    def choose(
        agent_id: str, matched_by: str, session_override: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        resolved_agent_id = pick_first_existing_agent_id(cfg, agent_id)
        override_scope = (
            session_override.get("dmScope")
            if isinstance(session_override, dict)
            else None
        )
        effective_dm_scope = override_scope if override_scope is not None else dm_scope
        session_key = build_agent_session_key(
            {
                "agentId": resolved_agent_id,
                "mainKey": session_cfg.get("mainKey") if session_cfg else None,
                "channel": channel,
                "accountId": account_id,
                "peer": peer,
                "dmScope": effective_dm_scope,
                "identityLinks": identity_links,
            }
        )
        main_session_key = normalize_lowercase_string_or_empty(
            build_agent_main_session_key(
                {
                    "agentId": resolved_agent_id,
                    "mainKey": session_cfg.get("mainKey") if session_cfg else None,
                }
            )
        )
        route = {
            "agentId": resolved_agent_id,
            "channel": channel,
            "accountId": account_id,
            "dmScope": effective_dm_scope,
            "sessionKey": session_key,
            "mainSessionKey": main_session_key,
            "lastRoutePolicy": derive_last_route_policy(
                {"sessionKey": session_key, "mainSessionKey": main_session_key}
            ),
            "matchedBy": matched_by,
        }
        if route_cache is not None and route_cache_key:
            route_cache[route_cache_key] = route
            if len(route_cache) > _MAX_RESOLVED_ROUTE_CACHE_KEYS:
                route_cache.clear()
                route_cache[route_cache_key] = route
        return route

    def format_peer(value: dict[str, Any] | None) -> str:
        if value and value.get("kind") and value.get("id"):
            return f"{value['kind']}:{value['id']}"
        return "none"

    def format_normalized_peer(value: dict[str, Any]) -> str:
        if value["state"] == "none":
            return "none"
        if value["state"] == "invalid":
            return "invalid"
        if value["state"] == "wildcard-kind":
            return f"{value['kind']}:*"
        return f"{value['kind']}:{value['id']}"

    if should_log_debug:
        log_debug(
            f"[routing] resolveAgentRoute: channel={channel} accountId={account_id} "
            f"peer={format_peer(peer)} guildId={guild_id or 'none'} "
            f"teamId={team_id or 'none'} bindings={len(bindings)}"
        )
        for entry in bindings:
            roles = entry["match"]["roles"]
            log_debug(
                f"[routing] binding: agentId={entry['binding'].get('agentId')} "
                f"accountPattern={entry['match']['accountPattern'] or 'default'} "
                f"peer={format_normalized_peer(entry['match']['peer'])} "
                f"guildId={entry['match']['guildId'] if entry['match']['guildId'] is not None else 'none'} "
                f"teamId={entry['match']['teamId'] if entry['match']['teamId'] is not None else 'none'} "
                f"roles={len(roles) if roles else 0}"
            )

    # Thread parent inheritance: if peer (thread) didn't match, check parent peer binding
    base_scope = {
        "guildId": guild_id,
        "teamId": team_id,
        "memberRoleIds": member_role_id_set,
    }

    tiers: list[dict[str, Any]] = [
        {
            "matchedBy": "binding.peer",
            "enabled": bool(peer),
            "scopePeer": peer,
            "candidates": _collect_peer_indexed_bindings(bindings_index, peer),
            "predicate": lambda candidate: candidate["match"]["peer"]["state"] == "valid",
        },
        {
            "matchedBy": "binding.peer.parent",
            "enabled": bool(parent_peer and parent_peer["id"]),
            "scopePeer": parent_peer if parent_peer and parent_peer["id"] else None,
            "candidates": _collect_peer_indexed_bindings(bindings_index, parent_peer),
            "predicate": lambda candidate: candidate["match"]["peer"]["state"] == "valid",
        },
        {
            "matchedBy": "binding.peer.wildcard",
            "enabled": bool(peer),
            "scopePeer": peer,
            "candidates": bindings_index["byPeerWildcard"],
            "predicate": lambda candidate: candidate["match"]["peer"]["state"] == "wildcard-kind",
        },
        {
            "matchedBy": "binding.guild+roles",
            "enabled": bool(guild_id and len(member_role_ids) > 0),
            "scopePeer": peer,
            "candidates": bindings_index["byGuildWithRoles"].get(guild_id, []) if guild_id else [],
            "predicate": lambda candidate: _has_guild_constraint(candidate["match"])
            and _has_roles_constraint(candidate["match"]),
        },
        {
            "matchedBy": "binding.guild",
            "enabled": bool(guild_id),
            "scopePeer": peer,
            "candidates": bindings_index["byGuild"].get(guild_id, []) if guild_id else [],
            "predicate": lambda candidate: _has_guild_constraint(candidate["match"])
            and not _has_roles_constraint(candidate["match"]),
        },
        {
            "matchedBy": "binding.team",
            "enabled": bool(team_id),
            "scopePeer": peer,
            "candidates": bindings_index["byTeam"].get(team_id, []) if team_id else [],
            "predicate": lambda candidate: _has_team_constraint(candidate["match"]),
        },
        {
            "matchedBy": "binding.account",
            "enabled": True,
            "scopePeer": peer,
            "candidates": bindings_index["byAccount"],
            "predicate": lambda candidate: candidate["match"]["accountPattern"] != "*",
        },
        {
            "matchedBy": "binding.channel",
            "enabled": True,
            "scopePeer": peer,
            "candidates": bindings_index["byChannel"],
            "predicate": lambda candidate: candidate["match"]["accountPattern"] == "*",
        },
    ]

    for tier in tiers:
        if not tier["enabled"]:
            continue
        matched = None
        for candidate in tier["candidates"]:
            if tier["predicate"](candidate) and _matches_binding_scope(
                candidate["match"], {**base_scope, "peer": tier["scopePeer"]}
            ):
                matched = candidate
                break
        if matched is not None:
            if should_log_debug:
                log_debug(
                    f"[routing] match: matchedBy={tier['matchedBy']} "
                    f"agentId={matched['binding'].get('agentId')}"
                )
            return choose(
                matched["binding"].get("agentId"),
                tier["matchedBy"],
                matched["binding"].get("session"),
            )

    return choose(resolve_default_agent_id(cfg), "default")


def reset_resolve_route_caches_for_tests() -> None:
    """Clear all module-level caches (test seam; TS relies on WeakMap GC)."""
    _agent_lookup_cache_by_cfg.clear()
    _evaluated_bindings_cache_by_cfg.clear()
    _resolved_route_cache_by_cfg.clear()


__all__ = [
    "build_agent_session_key",
    "derive_last_route_policy",
    "pick_first_existing_agent_id",
    "reset_resolve_route_caches_for_tests",
    "resolve_agent_route",
    "resolve_inbound_last_route_session_key",
    "set_routing_log_hooks",
]
