"""jarvis.shared.device_pairing_access — pairing access classification.

OpenClaw parity: mirrors ``openclaw-main/src/shared/device-pairing-access.ts``.
"""
from __future__ import annotations

from typing import Any, List, Optional, Set, TypedDict

from .device_auth import normalize_device_auth_scopes


class DevicePairingAccessSummary(TypedDict, total=False):
    """Access summary for a paired or pending device.

    Mirrors :type:`DevicePairingAccessSummary`
    (``shared/device-pairing-access.ts``).
    """
    roles: List[str]
    scopes: List[str]


PendingDeviceApprovalKind = str  # "new-pairing" | "role-upgrade" | "scope-upgrade" | "re-approval"


class PendingDeviceApprovalState(TypedDict, total=False):
    kind: str
    requested: DevicePairingAccessSummary
    approved: Optional[DevicePairingAccessSummary]


def _normalize_unique_single_or_trimmed_string_list(value) -> List[str]:
    """Drop non-strings, trim, dedupe (preserves first-seen order)."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        return []
    seen: Set[str] = set()
    out: List[str] = []
    for v in items:
        if isinstance(v, str):
            t = v.strip()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def _normalize_role_list(*items) -> List[str]:
    roles: Set[str] = set()
    for item in items:
        for role in _normalize_unique_single_or_trimmed_string_list(item):
            roles.add(role)
    return sorted(roles)


def _includes_all(allowed, requested) -> bool:
    s = set(allowed)
    return all(r in s for r in requested)


def _summarize_pending_device_access(request: dict) -> DevicePairingAccessSummary:
    return {
        "roles": _normalize_role_list(request.get("roles"), request.get("role")),
        "scopes": normalize_device_auth_scopes(request.get("scopes")),
    }


def _summarize_approved_device_access(device: dict) -> DevicePairingAccessSummary:
    approved_roles = _normalize_role_list(device.get("roles"), device.get("role"))
    tokens = device.get("tokens")
    if isinstance(tokens, list):
        token_list = tokens
    elif isinstance(tokens, dict):
        token_list = list(tokens.values())
    else:
        token_list = None
    if token_list is None:
        active_roles = approved_roles
    else:
        active_roles = _normalize_role_list(
            t.get("role") for t in token_list if not t.get("revokedAtMs")
        )
        active_roles = [r for r in active_roles if r in approved_roles]
    return {
        "roles": active_roles,
        "scopes": normalize_device_auth_scopes(device.get("scopes")),
    }


def resolve_pending_device_approval_state(
    request: dict, paired: Optional[dict] = None
) -> PendingDeviceApprovalState:
    """Classify a pending pairing request as new / role-upgrade / scope-upgrade / re-approval.

    Mirrors :func:`resolvePendingDeviceApprovalState`
    (``shared/device-pairing-access.ts``).
    """
    requested = _summarize_pending_device_access(request)
    approved = _summarize_approved_device_access(paired) if paired else None
    if not approved:
        return {"kind": "new-pairing", "requested": requested, "approved": None}
    if not _includes_all(approved["roles"], requested["roles"]):
        return {"kind": "role-upgrade", "requested": requested, "approved": approved}
    if not _includes_all(approved["scopes"], requested["scopes"]):
        return {"kind": "scope-upgrade", "requested": requested, "approved": approved}
    return {"kind": "re-approval", "requested": requested, "approved": approved}


__all__ = [
    "DevicePairingAccessSummary",
    "PendingDeviceApprovalKind",
    "PendingDeviceApprovalState",
    "resolve_pending_device_approval_state",
]
