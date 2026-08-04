"""jarvis.shared.device_bootstrap_profile — device bootstrap profile helpers.

OpenClaw parity: mirrors
``openclaw-main/src/shared/device-bootstrap-profile.ts``.
"""
from __future__ import annotations

from typing import List, Optional, TypedDict

from .device_auth import normalize_device_auth_role, normalize_device_auth_scopes


#: Closed purpose codes carried by specialized bootstrap tokens.
DeviceBootstrapPurpose = str  # "control-ui" | "mobile-full"


class DeviceBootstrapProfile(TypedDict, total=False):
    """Normalized roles/scopes carried by a bootstrap token during device handoff.

    Mirrors :type:`DeviceBootstrapProfile`
    (``shared/device-bootstrap-profile.ts``).
    """
    roles: List[str]
    scopes: List[str]
    purpose: DeviceBootstrapPurpose


class DeviceBootstrapProfileInput(TypedDict, total=False):
    roles: List[str]
    scopes: List[str]
    purpose: DeviceBootstrapPurpose


#: Operator scopes allowed to cross the short-lived bootstrap handoff boundary.
BOOTSTRAP_HANDOFF_OPERATOR_SCOPES = (
    "operator.approvals",
    "operator.questions",
    "operator.read",
    "operator.talk.secrets",
    "operator.write",
)

#: Full native-mobile operator scopes (adds admin).
MOBILE_FULL_ACCESS_OPERATOR_SCOPES = (
    "operator.admin",
    *BOOTSTRAP_HANDOFF_OPERATOR_SCOPES,
)

_BOOTSTRAP_HANDOFF_OPERATOR_SCOPE_SET = frozenset(BOOTSTRAP_HANDOFF_OPERATOR_SCOPES)
_MOBILE_FULL_ACCESS_OPERATOR_SCOPE_SET = frozenset(MOBILE_FULL_ACCESS_OPERATOR_SCOPES)


#: Existing least-privilege setup-code/QR profile.
PAIRING_SETUP_BOOTSTRAP_PROFILE: DeviceBootstrapProfile = {
    "roles": ["node", "operator"],
    "scopes": list(BOOTSTRAP_HANDOFF_OPERATOR_SCOPES),
}


#: Full native-mobile setup profile for explicitly authorized setup surfaces.
FULL_ACCESS_PAIRING_SETUP_BOOTSTRAP_PROFILE: DeviceBootstrapProfile = {
    "roles": ["node", "operator"],
    "scopes": list(MOBILE_FULL_ACCESS_OPERATOR_SCOPES),
    "purpose": "mobile-full",
}


#: Node-only setup profile for companions that never act as operators.
NODE_PAIRING_SETUP_BOOTSTRAP_PROFILE: DeviceBootstrapProfile = {
    "roles": ["node"],
    "scopes": [],
}


def _normalize_bootstrap_roles(roles) -> List[str]:
    if not isinstance(roles, list):
        return []
    out: set = set()
    for r in roles:
        norm = normalize_device_auth_role(r or "")
        if norm:
            out.add(norm)
    return sorted(out)


def _normalize_purpose(value) -> Optional[str]:
    if value in ("control-ui", "mobile-full"):
        return value
    return None


def normalize_device_bootstrap_profile(
    input_: Optional[DeviceBootstrapProfileInput] = None,
) -> DeviceBootstrapProfile:
    """Normalize caller-provided bootstrap roles/scopes without applying handoff bounds.

    Mirrors :func:`normalizeDeviceBootstrapProfile`
    (``shared/device-bootstrap-profile.ts``).
    """
    input_ = input_ or {}
    purpose = _normalize_purpose(input_.get("purpose"))
    out: DeviceBootstrapProfile = {
        "roles": _normalize_bootstrap_roles(input_.get("roles")),
        "scopes": normalize_device_auth_scopes(list(input_.get("scopes") or [])),
    }
    if purpose is not None:
        out["purpose"] = purpose
    return out


def device_bootstrap_profiles_equal(
    left: Optional[DeviceBootstrapProfileInput] = None,
    right: Optional[DeviceBootstrapProfileInput] = None,
) -> bool:
    """Compare normalized bootstrap profiles, including their closed purpose.

    Mirrors :func:`deviceBootstrapProfilesEqual`
    (``shared/device-bootstrap-profile.ts``).
    """
    l = normalize_device_bootstrap_profile(left)
    r = normalize_device_bootstrap_profile(right)
    return (
        l.get("purpose") == r.get("purpose")
        and l["roles"] == r["roles"]
        and l["scopes"] == r["scopes"]
    )


def resolve_bootstrap_profile_scopes_for_role(
    role: str, scopes, purpose: Optional[str] = None
) -> List[str]:
    """Resolve the subset of requested scopes a bootstrap profile may carry
    for one role.

    Mirrors :func:`resolveBootstrapProfileScopesForRole`
    (``shared/device-bootstrap-profile.ts``).
    """
    normalized_role = normalize_device_auth_role(role or "")
    normalized_scopes = normalize_device_auth_scopes(list(scopes or []))
    if normalized_role == "operator":
        allowed = (
            _MOBILE_FULL_ACCESS_OPERATOR_SCOPE_SET
            if purpose == "mobile-full"
            else _BOOTSTRAP_HANDOFF_OPERATOR_SCOPE_SET
        )
        return [s for s in normalized_scopes if s in allowed]
    return []


def resolve_bootstrap_profile_scopes_for_roles(
    roles, scopes, purpose: Optional[str] = None
) -> List[str]:
    return normalize_device_auth_scopes([
        s
        for role in roles or []
        for s in resolve_bootstrap_profile_scopes_for_role(role, scopes, purpose)
    ])


def resolve_device_profile_role_scopes(
    profile: DeviceBootstrapProfile, role: str, scopes=None
) -> List[str]:
    return resolve_bootstrap_profile_scopes_for_role(
        role, scopes if scopes is not None else profile.get("scopes") or [], profile.get("purpose")
    )


def resolve_device_profile_scopes(
    profile: DeviceBootstrapProfile, roles, scopes=None
) -> List[str]:
    return resolve_bootstrap_profile_scopes_for_roles(
        roles, scopes if scopes is not None else profile.get("scopes") or [], profile.get("purpose")
    )


def normalize_device_bootstrap_handoff_profile(
    input_: Optional[DeviceBootstrapProfileInput] = None,
) -> DeviceBootstrapProfile:
    """Normalize a requested bootstrap profile and strip scopes outside the
    handoff allowlist.

    Mirrors :func:`normalizeDeviceBootstrapHandoffProfile`
    (``shared/device-bootstrap-profile.ts``).
    """
    profile = normalize_device_bootstrap_profile(input_)
    out: DeviceBootstrapProfile = {
        "roles": profile["roles"],
        "scopes": resolve_bootstrap_profile_scopes_for_roles(
            profile["roles"], profile["scopes"], profile.get("purpose")
        ),
    }
    if profile.get("purpose") is not None:
        out["purpose"] = profile["purpose"]
    return out


def is_mobile_pairing_setup_bootstrap_profile(
    input_: Optional[DeviceBootstrapProfileInput] = None,
) -> bool:
    return device_bootstrap_profiles_equal(
        input_, PAIRING_SETUP_BOOTSTRAP_PROFILE
    ) or device_bootstrap_profiles_equal(
        input_, FULL_ACCESS_PAIRING_SETUP_BOOTSTRAP_PROFILE
    )


def is_node_pairing_setup_bootstrap_profile(
    input_: Optional[DeviceBootstrapProfileInput] = None,
) -> bool:
    return device_bootstrap_profiles_equal(
        input_, NODE_PAIRING_SETUP_BOOTSTRAP_PROFILE
    )


__all__ = [
    "DeviceBootstrapPurpose",
    "DeviceBootstrapProfile",
    "DeviceBootstrapProfileInput",
    "BOOTSTRAP_HANDOFF_OPERATOR_SCOPES",
    "MOBILE_FULL_ACCESS_OPERATOR_SCOPES",
    "PAIRING_SETUP_BOOTSTRAP_PROFILE",
    "FULL_ACCESS_PAIRING_SETUP_BOOTSTRAP_PROFILE",
    "NODE_PAIRING_SETUP_BOOTSTRAP_PROFILE",
    "normalize_device_bootstrap_profile",
    "device_bootstrap_profiles_equal",
    "resolve_bootstrap_profile_scopes_for_role",
    "resolve_bootstrap_profile_scopes_for_roles",
    "resolve_device_profile_role_scopes",
    "resolve_device_profile_scopes",
    "normalize_device_bootstrap_handoff_profile",
    "is_mobile_pairing_setup_bootstrap_profile",
    "is_node_pairing_setup_bootstrap_profile",
]
