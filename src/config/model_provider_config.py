"""jarvis.config.model_provider_config — model-provider config resolver.

OpenClaw parity: mirrors
``openclaw-main/src/config/model-provider-config.ts``.

Focused minimal port: thin facade that delegates provider-id
normalization + model catalog parsing to caller-provided callables
until those subsystems land.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


def _is_record(value) -> bool:
    return isinstance(value, dict) and not isinstance(value, (list, tuple, str, bytes, set))


def _normalize_provider_id(provider: str) -> str:
    if not isinstance(provider, str):
        return ""
    return provider.strip().lower()


def resolve_merged_model_provider_models(
    params: dict,
    *,
    normalize_model_id: Optional[Callable[[str], Optional[str]]] = None,
) -> dict:
    """Index configured model rows after caller-owned model-id normalization.

    Mirrors :func:`resolveMergedModelProviderModels`
    (``shared/config/model-provider-config.ts`).
    """
    models = params.get("models") or []
    if not callable(normalize_model_id):
        return {}
    out: dict = {}
    for model in models:
        if not _is_record(model):
            continue
        mid = model.get("id")
        if not isinstance(mid, str):
            continue
        model_id = normalize_model_id(mid)
        if not model_id:
            continue
        existing = out.get(model_id)
        # Earlier rows stay authoritative; later duplicates only supply missing fields.
        out[model_id] = {**model, **(existing or {})} if existing else model
    return out


def resolve_merged_model_provider_config(
    config: Any,
    provider: str,
) -> Optional[dict]:
    """Resolve only the merged provider config when its canonical key is not needed.

    Mirrors :func:`resolveMergedModelProviderConfig`
    (``shared/config/model-provider-config.ts`).
    """
    return resolve_merged_model_provider_entry(config, provider).get("providerConfig") if resolve_merged_model_provider_entry(config, provider) else None


def resolve_merged_model_provider_entry(config: Any, provider: str) -> Optional[dict]:
    """Resolve the provider entry produced by models-config key normalization.

    Mirrors :func:`resolveMergedModelProviderEntry`
    (``shared/config/model-provider-config.ts`).
    """
    if not isinstance(config, dict):
        return None
    requested_provider = provider.strip() if isinstance(provider, str) else ""
    normalized_provider = _normalize_provider_id(requested_provider)
    if not normalized_provider:
        return None
    providers_obj = (config.get("models") or {}).get("providers") or {}
    if not _is_record(providers_obj):
        return None
    providers = list(providers_obj.items())
    # exact-key first, then case-insensitive fallback.
    exact_key: Optional[str] = None
    fallback_key: Optional[str] = None
    for provider_id, _ in providers:
        if not isinstance(provider_id, str):
            continue
        if provider_id.strip() == requested_provider:
            exact_key = provider_id
            break
        if _normalize_provider_id(provider_id) == normalized_provider:
            fallback_key = provider_id
    provider_key = (exact_key or fallback_key)
    if not provider_key:
        return None
    matched: Optional[dict] = None
    for provider_id, provider_config in providers:
        if provider_id != provider_key:
            continue
        if not _is_record(provider_config):
            continue
        if matched is None:
            matched = dict(provider_config)
        else:
            # Later fields win, but omitted models keep the earlier catalog.
            next_models = provider_config.get("models", matched.get("models"))
            matched = {**matched, **provider_config, "models": next_models}
    if matched is None:
        return None
    return {"providerKey": provider_key, "providerConfig": matched}


__all__ = [
    "resolve_merged_model_provider_models",
    "resolve_merged_model_provider_config",
    "resolve_merged_model_provider_entry",
]
