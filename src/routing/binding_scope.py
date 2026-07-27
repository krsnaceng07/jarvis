"""jarvis.routing.binding_scope — route-binding scope normalization + matching.

OpenClaw parity: mirrors ``src/routing/binding-scope.ts``.

Route binding scopes constrain a configured agent/account binding to a
guild, team, group space, and optionally channel/platform role ids.
"""

from __future__ import annotations

from typing import Any, Iterable

from jarvis_normalization_core.string_coerce import normalize_lowercase_string_or_empty

from .account_id import normalize_account_id
from .agent_id import normalize_agent_id
from .channel_ids import normalize_chat_channel_id


def normalize_route_binding_id(value: object) -> str:
    """Mirrors ``normalizeRouteBindingId``: strings trim; numbers (incl.
    JS bigint — any Python int) stringify then trim; else ``""``."""
    if isinstance(value, str):
        return value.strip()
    # bool is an int subclass in Python; JS has no such coercion — exclude it.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float):
            # Match JS String(number) for integral floats (e.g. 42.0 -> "42").
            return str(int(value)).strip() if value.is_integer() else str(value).strip()
        return str(value).strip()
    return ""


def normalize_route_binding_roles(value: object) -> list[str] | None:
    """Mirrors ``normalizeRouteBindingRoles``: non-empty array or ``None``
    (an empty array means no role restriction)."""
    return value if isinstance(value, list) and len(value) > 0 else None


def normalize_route_binding_channel_id(raw: object) -> str | None:
    """Mirrors ``normalizeRouteBindingChannelId``: catalog-canonical id when
    known, else the raw lowered id, else ``None``."""
    normalized = normalize_chat_channel_id(raw)
    if normalized:
        return normalized
    fallback = normalize_lowercase_string_or_empty(raw)
    return fallback or None


def resolve_normalized_route_binding_match(binding: Any) -> dict[str, str] | None:
    """Convert a binding match into the same canonical ids used by session
    routing. Wildcard/malformed account matches are ignored because they
    are not concrete. Mirrors ``resolveNormalizedRouteBindingMatch``."""
    if not binding or not isinstance(binding, dict):
        return None
    match = binding.get("match")
    if not match or not isinstance(match, dict):
        return None
    channel_id = normalize_route_binding_channel_id(match.get("channel"))
    if not channel_id:
        return None
    raw_account_id = match.get("accountId")
    account_id = raw_account_id.strip() if isinstance(raw_account_id, str) else ""
    if not account_id or account_id == "*":
        return None
    return {
        "agentId": normalize_agent_id(binding.get("agentId")),
        "accountId": normalize_account_id(account_id),
        "channelId": channel_id,
    }


def _scope_id_matches(constraint: object, exact: str, group_space: str) -> bool:
    if not constraint:
        return True
    return constraint == exact or constraint == group_space


def _has_any_route_binding_role(roles: list[str], member_role_ids: object) -> bool:
    if not member_role_ids:
        return False
    has = getattr(member_role_ids, "has", None)
    if callable(has):
        # Duck-typed Set-like lookup (mirrors the TS `has` fast path).
        return any(has(role) for role in roles)
    if isinstance(member_role_ids, (set, frozenset)):
        return any(role in member_role_ids for role in roles)
    # Most callers pass a set, but arrays/iterables from channel adapters are
    # accepted to avoid forcing allocation at every routing call site.
    member_role_id_set = set(member_role_ids)  # type: ignore[arg-type]
    return any(role in member_role_id_set for role in roles)


def route_binding_scope_matches(constraint: dict[str, Any], scope: dict[str, Any]) -> bool:
    """Mirrors ``routeBindingScopeMatches``.

    ``constraint``: guildId?, teamId?, roles?.
    ``scope``: guildId?, teamId?, groupSpace?, memberRoleIds? (iterable).
    """
    guild_id = normalize_route_binding_id(scope.get("guildId"))
    team_id = normalize_route_binding_id(scope.get("teamId"))
    group_space = normalize_route_binding_id(scope.get("groupSpace"))
    if not _scope_id_matches(constraint.get("guildId"), guild_id, group_space):
        return False
    if not _scope_id_matches(constraint.get("teamId"), team_id, group_space):
        return False

    roles = normalize_route_binding_roles(constraint.get("roles"))
    if not roles:
        return True
    return _has_any_route_binding_role(roles, scope.get("memberRoleIds"))


__all__ = [
    "normalize_route_binding_channel_id",
    "normalize_route_binding_id",
    "normalize_route_binding_roles",
    "resolve_normalized_route_binding_match",
    "route_binding_scope_matches",
]
