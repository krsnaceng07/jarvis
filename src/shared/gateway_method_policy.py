"""jarvis.shared.gateway_method_policy — reserved gateway-method scope.

OpenClaw parity: mirrors ``openclaw-main/src/shared/gateway-method-policy.ts``.
"""
from __future__ import annotations

from typing import TypeVar

TScope = TypeVar("TScope", bound=str)

#: Reserved admin-only gateway method prefixes.
_RESERVED_ADMIN_GATEWAY_METHOD_PREFIXES = (
    "exec.approvals.",
    "config.",
    "wizard.",
    "update.",
)

#: The mandatory scope for reserved gateway methods.
RESERVED_ADMIN_GATEWAY_METHOD_SCOPE = "operator.admin"


def _is_reserved_admin_gateway_method(method: str) -> bool:
    return any(method.startswith(p) for p in _RESERVED_ADMIN_GATEWAY_METHOD_PREFIXES)


def resolve_reserved_gateway_method_scope(method: str):
    """Resolve the mandatory scope for a reserved gateway method.

    Mirrors :func:`resolveReservedGatewayMethodScope`
    (``shared/gateway-method-policy.ts``).
    """
    if not _is_reserved_admin_gateway_method(method):
        return None
    return RESERVED_ADMIN_GATEWAY_METHOD_SCOPE


def normalize_plugin_gateway_method_scope(method: str, scope):
    """Coerce plugin-declared scopes away from unsafe reserved scopes.

    Mirrors :func:`normalizePluginGatewayMethodScope`
    (``shared/gateway-method-policy.ts``).
    """
    reserved_scope = resolve_reserved_gateway_method_scope(method)
    if not reserved_scope or not scope or scope == reserved_scope:
        return {"scope": scope, "coercedToReservedAdmin": False}
    return {"scope": reserved_scope, "coercedToReservedAdmin": True}


__all__ = [
    "RESERVED_ADMIN_GATEWAY_METHOD_SCOPE",
    "resolve_reserved_gateway_method_scope",
    "normalize_plugin_gateway_method_scope",
]
