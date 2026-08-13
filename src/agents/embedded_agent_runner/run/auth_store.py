"""jarvis.agents.embedded_agent_runner.run.auth_store — create a scoped auth-profile store.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/auth-store.ts``.

Public surface:

- :func:`create_scoped_auth_profile_store`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

import json
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Auth profile store shape.
AuthProfileStore = Dict[str, Any]

_DEFAULT_AUTH_PROFILE_STORE: Dict[str, Any] = {"version": 1, "profiles": {}}


class PersistentProfileMap(dict):
    """Persist profile mutations immediately to the agent-level store."""

    def __init__(self, values: Any = None, *, parent: Optional["PersistentAuthProfileStore"] = None) -> None:
        super().__init__()
        self._parent = parent
        if isinstance(values, dict):
            super().update(values)

    def _save(self) -> None:
        if self._parent is not None:
            self._parent._save()

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)
        self._save()

    def __delitem__(self, key: Any) -> None:
        super().__delitem__(key)
        self._save()

    def update(self, *args: Any, **kwargs: Any) -> None:
        super().update(*args, **kwargs)
        self._save()

    def setdefault(self, key: Any, default: Any = None) -> Any:
        result = super().setdefault(key, default)
        self._save()
        return result

    def clear(self) -> None:
        super().clear()
        self._save()

    def pop(self, key: Any, default: Any = None) -> Any:
        result = super().pop(key, default)
        self._save()
        return result

    def popitem(self) -> tuple[Any, Any]:
        result = super().popitem()
        self._save()
        return result


class PersistentAuthProfileStore(dict):
    """Persist auth-profile updates to the agent dir immediately."""

    def __init__(self, value: Any = None, *, agent_dir: Optional[str] = None) -> None:
        super().__init__()
        self._agent_dir = agent_dir if isinstance(agent_dir, str) else None
        initial = _coerce_auth_profile_store(value)
        profiles = PersistentProfileMap(initial.get("profiles", {}), parent=self)
        super().update({
            "version": initial.get("version", 1),
            "profiles": profiles,
        })
        self._save()

    def _save(self) -> None:
        if not self._agent_dir:
            return
        path = _profile_store_path(self._agent_dir)
        if not path:
            return
        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(dict(self), handle, indent=2, sort_keys=True)

    def __setitem__(self, key: Any, value: Any) -> None:
        if key == "profiles":
            if isinstance(value, dict) and not isinstance(value, PersistentProfileMap):
                value = PersistentProfileMap(value, parent=self)
        super().__setitem__(key, value)
        self._save()

    def __delitem__(self, key: Any) -> None:
        super().__delitem__(key)
        self._save()

    def update(self, *args: Any, **kwargs: Any) -> None:
        data = dict(*args, **kwargs)
        if "profiles" in data and isinstance(data["profiles"], dict):
            data["profiles"] = PersistentProfileMap(data["profiles"], parent=self)
        super().update(data)
        self._save()

    def setdefault(self, key: Any, default: Any = None) -> Any:
        result = super().setdefault(key, default)
        self._save()
        return result

    def clear(self) -> None:
        super().clear()
        self._save()

    def pop(self, key: Any, default: Any = None) -> Any:
        result = super().pop(key, default)
        self._save()
        return result

    def popitem(self) -> tuple[Any, Any]:
        result = super().popitem()
        self._save()
        return result


def _canonicalize_profile_key(key: Any) -> Any:
    """Normalize legacy provider-scoped profile ids to canonical OpenAI ids."""
    if not isinstance(key, str):
        return key
    normalized = key.strip()
    if not normalized:
        return normalized
    if normalized.startswith("openai-codex:"):
        suffix = normalized.split(":", 1)[1]
        return f"openai:{suffix}"
    return normalized


def _canonicalize_profile_entry(profile_id: Any, profile: Any) -> Any:
    """Normalize a stored profile entry to canonical provider/profile shape."""
    if not isinstance(profile, dict):
        return profile
    canonical_profile = dict(profile)
    provider = canonical_profile.get("provider")
    if provider == "openai-codex":
        canonical_profile["provider"] = "openai"
    if isinstance(profile_id, str) and profile_id.startswith("openai-codex:"):
        canonical_profile["legacyProfileId"] = profile_id
    return canonical_profile


def _coerce_auth_profile_store(value: Any) -> Dict[str, Any]:
    """Normalize an auth-profile store dict to the canonical shape."""
    if not isinstance(value, dict):
        return {"version": 1, "profiles": {}}
    profiles = value.get("profiles")
    if not isinstance(profiles, dict):
        profiles = {}
    version = value.get("version", 1)
    canonical_profiles: Dict[str, Any] = {}
    for raw_key, raw_profile in profiles.items():
        key = _canonicalize_profile_key(raw_key)
        if key in canonical_profiles and raw_key != key:
            continue
        canonical_profiles[key] = _canonicalize_profile_entry(raw_key, raw_profile)
    return {
        "version": int(version) if isinstance(version, int) else 1,
        "profiles": canonical_profiles,
    }


def _profile_store_path(agent_dir: str) -> str:
    """Resolve the on-disk auth-profile store path for an agent dir."""
    if not isinstance(agent_dir, str) or not agent_dir.strip():
        return ""
    return os.path.join(agent_dir, "auth-profiles.json")


def _read_persisted_profile_store(agent_dir: str) -> Dict[str, Any]:
    path = _profile_store_path(agent_dir)
    if not path or not os.path.exists(path):
        return dict(_DEFAULT_AUTH_PROFILE_STORE)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, TypeError):
        return dict(_DEFAULT_AUTH_PROFILE_STORE)
    return _coerce_auth_profile_store(data)


def _write_persisted_profile_store(agent_dir: str, store: Dict[str, Any]) -> Dict[str, Any]:
    path = _profile_store_path(agent_dir)
    if not path:
        return store
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(store, handle, indent=2, sort_keys=True)
    return store


#: Installable hook for the create-scoped-auth-profile-store step.
_CREATE_SCOPED_AUTH_PROFILE_STORE: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {"version": 1, "profiles": {}}


def set_create_scoped_auth_profile_store_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom createScopedAuthProfileStore hook."""
    global _CREATE_SCOPED_AUTH_PROFILE_STORE
    _CREATE_SCOPED_AUTH_PROFILE_STORE = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_scoped_auth_profile_store(
    params: Dict[str, Any],
) -> AuthProfileStore:
    """Create a scoped auth-profile store.

    Mirrors :func:`createScopedAuthProfileStore`
    (``auth-store.ts``).

    The Python port persists the store under the agent directory as
    ``auth-profiles.json`` so the runtime keeps the last selected profiles
    across process restarts without changing the public hook surface.
    """
    raw_params = dict(params or {})
    custom_store = _CREATE_SCOPED_AUTH_PROFILE_STORE(raw_params)
    store = _coerce_auth_profile_store(custom_store)
    agent_dir = raw_params.get("agentDir") or raw_params.get("agent_dir")
    if isinstance(agent_dir, str) and agent_dir.strip():
        persisted = _read_persisted_profile_store(agent_dir)
        merged = {
            "version": max(int(store.get("version", 1)), int(persisted.get("version", 1))),
            "profiles": dict(persisted.get("profiles", {})),
        }
        merged["profiles"].update(dict(store.get("profiles", {})))
        store = PersistentAuthProfileStore(merged, agent_dir=agent_dir)
        store.update(merged)
        _write_persisted_profile_store(agent_dir, dict(store))
    else:
        store = PersistentAuthProfileStore(store)
    return store


__all__ = [
    "AuthProfileStore",
    "create_scoped_auth_profile_store",
    "set_create_scoped_auth_profile_store_hook",
]
