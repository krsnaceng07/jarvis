from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import json
from pathlib import Path

from src.sessions.auth_storage import AuthStorage


@dataclass
class ModelRef:
    """Lightweight model reference used during the Layer-2 port.

    Fields mirror the important pieces OpenClaw expects: `id`, `name`,
    `provider`, plus a small set of runtime metadata that higher layers
    (agent/session) will need: `context_window`, `auth_profile`, and
    provider-specific `params`.
    """
    id: str
    name: str
    provider: str
    params: Dict[str, Any] = field(default_factory=dict)
    #: Effective context window (tokens) to use for compaction budgeting
    context_window: Optional[int] = None
    #: Optional auth profile id that supplies credentials for the model
    auth_profile: Optional[str] = None
    #: Optional approximate cost per 1k tokens (for selection heuristics)
    cost_per_1k: Optional[float] = None


class ModelRegistry:
    """Minimal model registry placeholder.

    This is a starting point for the OpenClaw `model-registry` port.
    It provides in-memory registration and simple resolution by name.
    More features (provider-specific metadata, weight maps, discovery)
    will be added during the full port.
    """

    def __init__(self) -> None:
        self._models_by_name: Dict[str, ModelRef] = {}
        self._models_by_id: Dict[str, ModelRef] = {}

    def register(self, model: ModelRef) -> None:
        self._models_by_name[model.name] = model
        self._models_by_id[model.id] = model

    def resolve(self, name_or_id: str) -> Optional[ModelRef]:
        # Try lookup by id, then by name
        if name_or_id in self._models_by_id:
            return self._models_by_id[name_or_id]
        return self._models_by_name.get(name_or_id)

    def list_models(self) -> list[ModelRef]:
        return list(self._models_by_id.values())


# Module-level singleton for quick access during initial porting.
_REGISTRY = ModelRegistry()
_AUTH: AuthStorage | None = None


def _reset_runtime_state() -> None:
    """Clear the in-memory registry/auth state before reloading config.

    The registry is a process-global singleton; config reloads are expected
    to reflect the current workspace config rather than accumulate stale models
    from prior runs or prior tests.
    """
    global _REGISTRY, _AUTH
    _REGISTRY = ModelRegistry()
    _AUTH = None


def register_model(
    id: str,
    name: str,
    provider: str,
    params: Optional[Dict[str, Any]] = None,
    context_window: Optional[int] = None,
    auth_profile: Optional[str] = None,
    cost_per_1k: Optional[float] = None,
) -> None:
    params = params or {}
    mr = ModelRef(
        id=id,
        name=name,
        provider=provider,
        params=params,
        context_window=context_window,
        auth_profile=auth_profile,
        cost_per_1k=cost_per_1k,
    )
    _REGISTRY.register(mr)


def resolve_model(name_or_id: str) -> Optional[ModelRef]:
    return _REGISTRY.resolve(name_or_id)


def list_models() -> list[ModelRef]:
    return _REGISTRY.list_models()


def populate_from_config(config_path: Path | str | None = None) -> None:
    """Populate the module registry from a JSON config file.

    Expected config shapes supported (flexible to match OpenClaw variants):
    - { "models": [ { id, name, provider, params, context_window, auth_profile, cost_per_1k }, ... ] }
    - fallback: { "providers": { "default": "gemini" }, "model": "gemini-2.0-flash" }

    The function is intentionally tolerant: missing fields are ignored and
    a sensible default entry is created when only a default provider/model
    is present.
    """
    global _AUTH
    _reset_runtime_state()
    path = Path(config_path) if config_path is not None else Path("config/jarvis.json")
    if not path.exists():
        # Still attempt to load api_keys from default location even when jarvis.json missing
        api_path = path.parent / "api_keys.json"
        _AUTH = AuthStorage.load_from_file(api_path)
        return

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return
    except Exception:
        return

    # Load auth storage from api_keys.json sibling to the config when present
    api_path = path.parent / "api_keys.json"
    _AUTH = AuthStorage.load_from_file(api_path)

    models = raw.get("models")
    if isinstance(models, list):
        for m in models:
            if not isinstance(m, dict):
                continue
            mid = str(m.get("id") or m.get("name") or f"model-{len(_REGISTRY.list_models())}")
            name = str(m.get("name") or mid)
            provider = str(m.get("provider") or raw.get("providers", {}).get("default", ""))
            params = m.get("params") or {}
            # accept both snake_case and camelCase config keys
            context_window = m.get("context_window") or m.get("contextWindow")
            auth_profile = m.get("auth_profile") or m.get("authProfile")
            cost = m.get("cost_per_1k") or m.get("costPer1k")
            register_model(
                id=mid,
                name=name,
                provider=provider,
                params=params,
                context_window=context_window,
                auth_profile=auth_profile,
                cost_per_1k=cost,
            )
        return

    # Fallback: if a default provider or model is present, register a single default model
    default_provider = None
    if isinstance(raw.get("providers"), dict):
        default_provider = raw["providers"].get("default")
    default_model_name = raw.get("model")
    if default_provider or default_model_name:
        mid = str(default_model_name or default_provider or "default")
        name = str(default_model_name or mid)
        provider = str(default_provider or name)
        register_model(id=mid, name=name, provider=provider)


def get_auth_storage() -> AuthStorage | None:
    """Return the loaded AuthStorage instance, or None if not loaded."""
    global _AUTH
    if _AUTH is None:
        init_from_default_paths()
    return _AUTH


def init_from_default_paths() -> None:
    """Shortcut to populate the registry and load auth storage from the
    repository-local default config paths: `config/jarvis.json` and
    `config/api_keys.json`.
    """
    populate_from_config(None)


def get_credentials_for_model(name_or_id: str) -> Optional[Any]:
    """Resolve credentials for a registered model.

    Resolution rules:
    - If the model has an explicit `auth_profile`, consult `AuthStorage.get_credentials(profile)`.
    - Otherwise, consult `AuthStorage.get_credentials(provider)`.
    - Returns None when no auth storage is loaded or no credentials found.
    """
    model = _REGISTRY.resolve(name_or_id)
    if model is None:
        return None
    auth = get_auth_storage()
    if auth is None:
        return None
    # If model.auth_profile is present, prefer it (it may be a profile key)
    if model.auth_profile:
        cred = auth.get_credentials(model.provider, profile_id=model.auth_profile)
        if cred is not None:
            return cred
    # Fall back to provider-named credentials
    return auth.get_credentials(model.provider)
