"""jarvis.shared.device_auth — device-auth types and scope normalizers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/device-auth.ts``.
"""
from __future__ import annotations

from typing import Dict, List, Optional, TypedDict


class DeviceAuthEntry(TypedDict):
    """Stored bearer-token metadata for one authorized device role.

    Mirrors :type:`DeviceAuthEntry` (``shared/device-auth.ts``).
    """
    token: str
    role: str
    scopes: List[str]
    updatedAtMs: int


class DeviceAuthStore(TypedDict):
    """Versioned on-disk device-auth cache for a gateway device identity.

    Mirrors :type:`DeviceAuthStore` (``shared/device-auth.ts``).
    """
    version: int  # literal 1
    deviceId: str
    tokens: Dict[str, DeviceAuthEntry]


def normalize_device_auth_role(role: str) -> str:
    """Normalize a device-auth role id without changing its case or namespace.

    Mirrors :func:`normalizeDeviceAuthRole` (``shared/device-auth.ts``).
    """
    return role.strip()


def normalize_device_auth_scopes(scopes: Optional[list]) -> List[str]:
    """Normalize device-auth scopes, dedupe/sort, and add operator implications.

    Mirrors :func:`normalizeDeviceAuthScopes` (``shared/device-auth.ts``).
    """
    if not isinstance(scopes, list):
        return []
    out: set = set()
    for scope in scopes:
        if not isinstance(scope, str):
            continue
        trimmed = scope.strip()
        if trimmed:
            out.add(trimmed)
    # Operator scope implication keeps older approval checks working with broader grants.
    if "operator.admin" in out:
        out.add("operator.read")
        out.add("operator.write")
    elif "operator.write" in out:
        out.add("operator.read")
    return sorted(out)


__all__ = [
    "DeviceAuthEntry",
    "DeviceAuthStore",
    "normalize_device_auth_role",
    "normalize_device_auth_scopes",
]
