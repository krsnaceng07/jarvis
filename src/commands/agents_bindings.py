"""jarvis.commands.agents_bindings — pure helpers for parsing, applying, and removing agent route bindings.

OpenClaw parity: mirrors ``src/commands/agents.bindings.ts``.

These are pure helpers that operate on config dicts. No I/O is performed
here; the CLI layer (agents_list_command.py, agents_bind_command.py) calls
these helpers and handles output + config file writes.

Key public surface:
  - ``parse_binding_specs`` — parse ``--bind`` flag strings into binding dicts
  - ``apply_agent_bindings`` — merge new bindings into config, detect conflicts
  - ``remove_agent_bindings`` — remove bindings by spec match
  - ``describe_binding`` — re-exported from binding_format
"""

from __future__ import annotations

import json
from typing import Any

from src.routing.agent_id import normalize_agent_id
from src.routing.session_key import DEFAULT_ACCOUNT_ID
from src.routing.config_bindings import list_route_bindings, is_route_binding
from .binding_format import describe_binding

__all__ = [
    "describe_binding",
    "parse_binding_specs",
    "apply_agent_bindings",
    "remove_agent_bindings",
]

# ---------------------------------------------------------------------------
# Binding match key helpers (mirrors TS bindingMatchKey / bindingMatchIdentityKey)
# ---------------------------------------------------------------------------


def _normalize_optional_string(value: object) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else ""
    return ""


def _binding_match_identity_key(match: dict[str, Any]) -> str:
    """Stable key for match criteria excluding accountId.

    Mirrors ``bindingMatchIdentityKey``.
    """
    roles_raw = match.get("roles")
    roles: list[str] = sorted(
        {str(r).strip() for r in roles_raw if isinstance(r, str) and r.strip()}
    ) if isinstance(roles_raw, list) else []

    peer = match.get("peer") or {}
    return json.dumps([
        match.get("channel") or "",
        peer.get("kind") if isinstance(peer, dict) else "",
        peer.get("id") if isinstance(peer, dict) else "",
        match.get("guildId") or "",
        match.get("teamId") or "",
        ",".join(roles),
    ])


def _binding_match_key(match: dict[str, Any]) -> str:
    """Full match key including accountId.

    Mirrors ``bindingMatchKey``.
    """
    account_id = _normalize_optional_string(match.get("accountId")) or DEFAULT_ACCOUNT_ID
    identity_key = _binding_match_identity_key(match)
    return json.dumps([identity_key, account_id])


def _can_upgrade_binding_account_scope(
    *,
    existing: dict[str, Any],
    incoming: dict[str, Any],
    normalized_incoming_agent_id: str,
) -> bool:
    """True when *incoming* upgrades *existing* from default to specific accountId.

    Mirrors ``canUpgradeBindingAccountScope``.
    """
    if not _normalize_optional_string(incoming.get("match", {}).get("accountId")):
        return False
    if _normalize_optional_string(existing.get("match", {}).get("accountId")):
        return False
    if normalize_agent_id(existing.get("agentId", "")) != normalized_incoming_agent_id:
        return False
    return (
        _binding_match_identity_key(existing.get("match") or {})
        == _binding_match_identity_key(incoming.get("match") or {})
    )


# ---------------------------------------------------------------------------
# apply_agent_bindings
# ---------------------------------------------------------------------------


def apply_agent_bindings(
    cfg: dict[str, Any],
    bindings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge new route bindings into config, detecting conflicts and upgrades.

    Mirrors ``applyAgentBindings``.

    Returns a result dict:
        {
            "config": <updated cfg>,
            "added": [...],
            "updated": [...],
            "skipped": [...],
            "conflicts": [{"binding": ..., "existingAgentId": ...}, ...],
        }
    """
    existing_routes: list[dict[str, Any]] = list(list_route_bindings(cfg))
    non_route_bindings: list[Any] = [
        b for b in (cfg.get("bindings") or []) if not is_route_binding(b)
    ]

    existing_match_map: dict[str, str] = {}
    for binding in existing_routes:
        key = _binding_match_key(binding.get("match") or {})
        if key not in existing_match_map:
            existing_match_map[key] = normalize_agent_id(binding.get("agentId", ""))

    added: list[dict] = []
    updated: list[dict] = []
    skipped: list[dict] = []
    conflicts: list[dict] = []

    merged_routes = list(existing_routes)

    for incoming in bindings:
        incoming_agent_id = normalize_agent_id(incoming.get("agentId", ""))
        match = incoming.get("match") or {}
        key = _binding_match_key(match)

        if key in existing_match_map:
            existing_agent_id = existing_match_map[key]
            if existing_agent_id == incoming_agent_id:
                skipped.append(incoming)
            else:
                conflicts.append({"binding": incoming, "existingAgentId": existing_agent_id})
            continue

        # Check for scope upgrade (default → specific accountId).
        upgraded = False
        for i, existing in enumerate(merged_routes):
            if _can_upgrade_binding_account_scope(
                existing=existing,
                incoming=incoming,
                normalized_incoming_agent_id=incoming_agent_id,
            ):
                merged_routes[i] = incoming
                updated.append(incoming)
                upgraded = True
                break

        if not upgraded:
            merged_routes.append(incoming)
            added.append(incoming)

    updated_cfg = {**cfg, "bindings": [*non_route_bindings, *merged_routes]}
    return {
        "config": updated_cfg,
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "conflicts": conflicts,
    }


# ---------------------------------------------------------------------------
# remove_agent_bindings
# ---------------------------------------------------------------------------


def remove_agent_bindings(
    cfg: dict[str, Any],
    bindings_to_remove: list[dict[str, Any]],
) -> dict[str, Any]:
    """Remove matching route bindings from config.

    Mirrors ``removeAgentBindings``.

    Returns ``{"config": ..., "removed": [...], "notFound": [...]}``.
    """
    remove_keys = {
        _binding_match_key(b.get("match") or {}) for b in bindings_to_remove
    }
    existing_routes = list(list_route_bindings(cfg))
    non_route_bindings = [b for b in (cfg.get("bindings") or []) if not is_route_binding(b)]

    kept: list[dict] = []
    removed: list[dict] = []
    for binding in existing_routes:
        key = _binding_match_key(binding.get("match") or {})
        if key in remove_keys:
            removed.append(binding)
            remove_keys.discard(key)
        else:
            kept.append(binding)

    not_found = [b for b in bindings_to_remove if _binding_match_key(b.get("match") or {}) in remove_keys]

    updated_cfg = {**cfg, "bindings": [*non_route_bindings, *kept]}
    return {"config": updated_cfg, "removed": removed, "notFound": not_found}


# ---------------------------------------------------------------------------
# parse_binding_specs
# ---------------------------------------------------------------------------

_PEER_KINDS = frozenset({"direct", "group", "channel"})


def _parse_single_binding_spec(
    *,
    agent_id: str,
    spec: str,
) -> dict[str, Any] | str:
    """Parse a ``--bind`` flag string into an AgentRouteBinding dict.

    Spec format (mirrors OpenClaw's ``--bind`` flag convention):
        <channel>[/<accountId>[/<peer-kind>:<peer-id>]]
        [?guild=<guildId>][&team=<teamId>][&roles=<r1,r2>]

    Examples:
        discord
        discord/support
        discord/default/channel:123456789
        slack/workspace?guild=GABCD
        discord?roles=ROLE1,ROLE2&guild=1234

    Returns the parsed binding dict or an error string.
    """
    spec = spec.strip()
    if not spec:
        return "Binding spec must not be empty."

    # Split query string
    query_str = ""
    if "?" in spec:
        spec, query_str = spec.split("?", 1)

    # Parse query params
    guild_id: str | None = None
    team_id: str | None = None
    roles: list[str] | None = None
    for part in query_str.split("&"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k == "guild":
                guild_id = v or None
            elif k == "team":
                team_id = v or None
            elif k == "roles":
                roles = [r.strip() for r in v.split(",") if r.strip()] or None
        else:
            return f"Unrecognized query param: {part!r}"

    # Parse path: channel[/accountId[/kind:id]]
    segments = spec.split("/")
    channel = segments[0].strip().lower()
    if not channel:
        return "Binding spec must start with a channel name."

    account_id: str | None = None
    peer: dict[str, str] | None = None

    if len(segments) >= 2:
        account_id = segments[1].strip() or None

    if len(segments) >= 3:
        peer_raw = segments[2].strip()
        if ":" in peer_raw:
            kind, peer_id = peer_raw.split(":", 1)
            kind = kind.strip().lower()
            peer_id = peer_id.strip()
            if kind not in _PEER_KINDS:
                return (
                    f"Unknown peer kind {kind!r}. Valid: {', '.join(sorted(_PEER_KINDS))}."
                )
            peer = {"kind": kind, "id": peer_id}
        else:
            return f"Peer must be in kind:id format, got {peer_raw!r}."

    match: dict[str, Any] = {"channel": channel}
    if account_id:
        match["accountId"] = account_id
    if peer:
        match["peer"] = peer
    if guild_id:
        match["guildId"] = guild_id
    if team_id:
        match["teamId"] = team_id
    if roles:
        match["roles"] = roles

    return {"agentId": agent_id, "match": match}


def parse_binding_specs(
    *,
    agent_id: str,
    specs: list[str],
    config: dict[str, Any] | None = None,  # noqa: ARG001 — reserved for future channel validation
) -> dict[str, Any]:
    """Parse a list of ``--bind`` spec strings into route binding dicts.

    Mirrors ``parseBindingSpecs``.

    Returns ``{"bindings": [...], "errors": [...]}``.
    """
    bindings: list[dict[str, Any]] = []
    errors: list[str] = []
    normalized_agent_id = normalize_agent_id(agent_id)

    for spec in specs:
        result = _parse_single_binding_spec(agent_id=normalized_agent_id, spec=spec)
        if isinstance(result, str):
            errors.append(f"Invalid binding spec {spec!r}: {result}")
        else:
            bindings.append(result)

    return {"bindings": bindings, "errors": errors}
