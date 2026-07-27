"""jarvis.routing.bindings — configured channel/agent route-binding helpers.

OpenClaw parity: mirrors ``src/routing/bindings.ts``. Public binding
helpers used by routing UI/diagnostics; they expose concrete account
ids derived from configured agent route bindings.
"""

from __future__ import annotations

from typing import Any

from .agent_id import normalize_agent_id
from .agent_scope import resolve_default_agent_id
from .binding_scope import (
    normalize_route_binding_channel_id,
    resolve_normalized_route_binding_match,
)
from .config_bindings import list_route_bindings


def list_bindings(cfg: dict[str, Any]) -> list[Any]:
    """Mirrors ``listBindings`` (= ``listRouteBindings``)."""
    return list_route_bindings(cfg)


def list_bound_account_ids(cfg: dict[str, Any], channel_id: str) -> list[str]:
    """Mirrors ``listBoundAccountIds``: sorted unique bound account ids."""
    normalized_channel = normalize_route_binding_channel_id(channel_id)
    if not normalized_channel:
        return []
    ids: set[str] = set()
    for binding in list_bindings(cfg):
        resolved = resolve_normalized_route_binding_match(binding)
        if not resolved or resolved["channelId"] != normalized_channel:
            continue
        ids.add(resolved["accountId"])
    return sorted(ids)


def resolve_default_agent_bound_account_id(cfg: dict[str, Any], channel_id: str) -> str | None:
    """Mirrors ``resolveDefaultAgentBoundAccountId``."""
    normalized_channel = normalize_route_binding_channel_id(channel_id)
    if not normalized_channel:
        return None
    default_agent_id = normalize_agent_id(resolve_default_agent_id(cfg))
    for binding in list_bindings(cfg):
        resolved = resolve_normalized_route_binding_match(binding)
        if (
            not resolved
            or resolved["channelId"] != normalized_channel
            or resolved["agentId"] != default_agent_id
        ):
            continue
        return resolved["accountId"]
    return None


def build_channel_account_bindings(cfg: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    """Mirrors ``buildChannelAccountBindings``.

    Map shape is channel -> agent -> accounts so callers can answer both
    "what accounts exist here" and "which accounts are bound to this agent".
    """
    mapping: dict[str, dict[str, list[str]]] = {}
    for binding in list_bindings(cfg):
        resolved = resolve_normalized_route_binding_match(binding)
        if not resolved:
            continue
        by_agent = mapping.setdefault(resolved["channelId"], {})
        accounts = by_agent.setdefault(resolved["agentId"], [])
        if resolved["accountId"] not in accounts:
            accounts.append(resolved["accountId"])
    return mapping


def resolve_preferred_account_id(params: dict[str, Any]) -> str:
    """Mirrors ``resolvePreferredAccountId`` (params: accountIds,
    defaultAccountId, boundAccounts)."""
    bound_accounts = params["boundAccounts"]
    if len(bound_accounts) > 0:
        first = bound_accounts[0]
        if first is None:
            raise ValueError("Expected bound accounts entry at 0 to be defined")
        return first
    return params["defaultAccountId"]


__all__ = [
    "build_channel_account_bindings",
    "list_bindings",
    "list_bound_account_ids",
    "resolve_default_agent_bound_account_id",
    "resolve_preferred_account_id",
]
