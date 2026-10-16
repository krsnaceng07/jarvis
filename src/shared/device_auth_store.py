"""jarvis.shared.device_auth_store — device-auth store helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/device-auth-store.ts``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .device_auth import (
    DeviceAuthEntry,
    DeviceAuthStore,
    normalize_device_auth_role,
    normalize_device_auth_scopes,
)


def _is_record(value: Any) -> bool:
    return isinstance(value, dict)


def _coerce_device_auth_entry(role: str, value: Any) -> Optional[DeviceAuthEntry]:
    if not _is_record(value) or not isinstance(value.get("token"), str):
        return None
    updated_at = value.get("updatedAtMs")
    if isinstance(updated_at, (int, float)) and updated_at == updated_at:  # not NaN
        updated_at_ms = int(updated_at) if updated_at == float(updated_at) and updated_at.is_integer() else 0
    else:
        updated_at_ms = 0
    scopes_raw = value.get("scopes")
    scopes = normalize_device_auth_scopes(scopes_raw if isinstance(scopes_raw, list) else None)
    return {
        "token": value["token"],
        "role": role,
        "scopes": scopes,
        "updatedAtMs": updated_at_ms,
    }


def _call_adapter(adapter: Any, method: str, *args) -> Any:
    """Call an adapter method either as a dict key (camelCase) or attribute.

    OpenClaw's adapter is ``{ readStore, writeStore }``; tests often pass a
    plain object with those attributes. Support both shapes.
    """
    if adapter is None:
        return None
    if isinstance(adapter, dict):
        fn = adapter.get(method)
    else:
        fn = getattr(adapter, method, None)
    if fn is None:
        return None
    return fn(*args)


def _copy_canonical_device_auth_tokens(tokens: Dict[str, Any]) -> Dict[str, DeviceAuthEntry]:
    out: Dict[str, DeviceAuthEntry] = {}
    for raw_role, value in tokens.items():
        role = normalize_device_auth_role(raw_role)
        if not role:
            continue
        entry = _coerce_device_auth_entry(role, value)
        if entry is not None:
            out[role] = entry
    return out


def coerce_device_auth_store(value: Any) -> Optional[DeviceAuthStore]:
    """Coerce raw persisted device-auth JSON into the canonical store shape.

    Mirrors :func:`coerceDeviceAuthStore` (``shared/device-auth-store.ts``).
    """
    if not _is_record(value) or value.get("version") != 1 or not isinstance(value.get("deviceId"), str):
        return None
    if not _is_record(value.get("tokens")):
        return None
    return {
        "version": 1,
        "deviceId": value["deviceId"],
        "tokens": _copy_canonical_device_auth_tokens(value["tokens"]),
    }


def load_device_auth_token_from_store(params: dict) -> Optional[DeviceAuthEntry]:
    """Load one normalized role token from the store.

    Mirrors :func:`loadDeviceAuthTokenFromStore`
    (``shared/device-auth-store.ts``).
    """
    adapter = params.get("adapter")
    device_id = params.get("deviceId")
    role = normalize_device_auth_role(params.get("role") or "")
    if not role:
        return None
    store = _call_adapter(adapter, "readStore")
    if not store or store.get("deviceId") != device_id:
        return None
    return _coerce_device_auth_entry(role, store.get("tokens", {}).get(role))


def store_device_auth_token_in_store(params: dict) -> DeviceAuthEntry:
    """Store one role token while preserving canonical tokens for the device id.

    Mirrors :func:`storeDeviceAuthTokenInStore`
    (``shared/device-auth-store.ts``).
    """
    import time
    adapter = params.get("adapter")
    device_id = params.get("deviceId")
    role = normalize_device_auth_role(params.get("role") or "")
    token = params.get("token")
    scopes = params.get("scopes")
    if not isinstance(token, str):
        raise ValueError("token must be a string")
    existing = _call_adapter(adapter, "readStore")
    if existing and existing.get("deviceId") == device_id and _is_record(existing.get("tokens")):
        tokens = _copy_canonical_device_auth_tokens(existing["tokens"])
    else:
        tokens = {}
    entry: DeviceAuthEntry = {
        "token": token,
        "role": role,
        "scopes": normalize_device_auth_scopes(scopes if isinstance(scopes, list) else None),
        "updatedAtMs": int(time.time() * 1000),
    }
    tokens[role] = entry
    next_store: DeviceAuthStore = {
        "version": 1,
        "deviceId": device_id,
        "tokens": tokens,
    }
    _call_adapter(adapter, "writeStore", next_store)
    return entry


def clear_device_auth_token_from_store(params: dict) -> None:
    """Clear one role token without rewriting missing or wrong-device stores.

    Mirrors :func:`clearDeviceAuthTokenFromStore`
    (``shared/device-auth-store.ts``).
    """
    adapter = params.get("adapter")
    device_id = params.get("deviceId")
    role = normalize_device_auth_role(params.get("role") or "")
    if not role:
        return
    store = _call_adapter(adapter, "readStore")
    if not store or store.get("deviceId") != device_id:
        return
    if role not in store.get("tokens", {}):
        return
    tokens = _copy_canonical_device_auth_tokens(store["tokens"])
    tokens.pop(role, None)
    _call_adapter(adapter, "writeStore", {
        "version": 1,
        "deviceId": store["deviceId"],
        "tokens": tokens,
    })


__all__ = [
    "coerce_device_auth_store",
    "load_device_auth_token_from_store",
    "store_device_auth_token_in_store",
    "clear_device_auth_token_from_store",
]
