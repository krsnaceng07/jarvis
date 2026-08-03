"""jarvis.shared.operator_scope_compat — operator role scope compatibility helpers.

OpenClaw parity: mirrors
``openclaw-main/src/shared/operator-scope-compat.ts``.

Public surface:

- :func:`role_scopes_allow`
- :func:`resolve_missing_requested_scope`
- :func:`resolve_scope_outside_requested_roles`
- :data:`OPERATOR_ROLE`
- :data:`OPERATOR_ADMIN_SCOPE`
- :data:`OPERATOR_READ_SCOPE`
- :data:`OPERATOR_WRITE_SCOPE`
"""
from __future__ import annotations

from typing import List, Optional, Set


OPERATOR_ROLE = "operator"
OPERATOR_ADMIN_SCOPE = "operator.admin"
OPERATOR_READ_SCOPE = "operator.read"
OPERATOR_WRITE_SCOPE = "operator.write"
OPERATOR_SCOPE_PREFIX = "operator."


def _normalize_scope_list(scopes) -> List[str]:
    out: Set[str] = set()
    for scope in scopes or []:
        if not isinstance(scope, str):
            continue
        cleaned = scope.strip()
        if cleaned:
            out.add(cleaned)
    return list(out)


def _operator_scope_satisfied(requested_scope: str, granted: Set[str]) -> bool:
    if not requested_scope.startswith(OPERATOR_SCOPE_PREFIX):
        return False
    if OPERATOR_ADMIN_SCOPE in granted:
        return True
    if requested_scope == OPERATOR_READ_SCOPE:
        return OPERATOR_READ_SCOPE in granted or OPERATOR_WRITE_SCOPE in granted
    if requested_scope == OPERATOR_WRITE_SCOPE:
        return OPERATOR_WRITE_SCOPE in granted
    return requested_scope in granted


def role_scopes_allow(params: dict) -> bool:
    """Return whether the role grant satisfies the requested scopes.

    Mirrors :func:`roleScopesAllow` (``shared/operator-scope-compat.ts``).
    """
    requested = _normalize_scope_list(params.get("requestedScopes"))
    if not requested:
        return True
    allowed = _normalize_scope_list(params.get("allowedScopes"))
    if not allowed:
        return False
    allowed_set = set(allowed)
    role = (params.get("role") or "").strip()
    if role != OPERATOR_ROLE:
        prefix = f"{role}."
        return all(scope.startswith(prefix) and scope in allowed_set for scope in requested)
    return all(_operator_scope_satisfied(scope, allowed_set) for scope in requested)


def resolve_missing_requested_scope(params: dict) -> Optional[str]:
    """Return the first requested scope not covered by the role's allowed scopes.

    Mirrors :func:`resolveMissingRequestedScope` (``shared/operator-scope-compat.ts``).
    """
    for scope in params.get("requestedScopes") or []:
        if not role_scopes_allow(
            {
                "role": params.get("role"),
                "requestedScopes": [scope],
                "allowedScopes": params.get("allowedScopes"),
            }
        ):
            return scope
    return None


def resolve_scope_outside_requested_roles(params: dict) -> Optional[str]:
    """Return the first requested scope that does not belong to any requested role.

    Mirrors :func:`resolveScopeOutsideRequestedRoles`
    (``shared/operator-scope-compat.ts``).
    """
    for scope in params.get("requestedScopes") or []:
        matches = any(
            role_scopes_allow(
                {
                    "role": role,
                    "requestedScopes": [scope],
                    "allowedScopes": [scope],
                }
            )
            for role in params.get("requestedRoles") or []
        )
        if not matches:
            return scope
    return None


__all__ = [
    "OPERATOR_ROLE",
    "OPERATOR_ADMIN_SCOPE",
    "OPERATOR_READ_SCOPE",
    "OPERATOR_WRITE_SCOPE",
    "OPERATOR_SCOPE_PREFIX",
    "role_scopes_allow",
    "resolve_missing_requested_scope",
    "resolve_scope_outside_requested_roles",
]
