"""Built-in provider-specific model-id normalization rules.

OpenClaw parity:
``packages/model-catalog-core/src/provider-model-id-normalize.ts``.
These are provider-owned facts (graduated preview ids, renamed models);
manifest policies layer on top in :mod:`provider_model_id_normalization`.
"""

from __future__ import annotations

#: Bare Antigravity pro ids that need the ``-low`` effort suffix.
_ANTIGRAVITY_BARE_PRO_IDS = frozenset({"gemini-3-pro", "gemini-3.1-pro", "gemini-3-1-pro"})

_GOOGLE_PROVIDER_PREFIX = "google/"


def normalize_google_preview_model_id(model_id: str) -> str:
    """Map graduated/deprecated Google preview ids to their current id."""
    if model_id.startswith(_GOOGLE_PROVIDER_PREFIX):
        bare = model_id[len(_GOOGLE_PROVIDER_PREFIX) :]
        normalized = normalize_google_preview_model_id(bare)
        return f"{_GOOGLE_PROVIDER_PREFIX}{normalized}" if normalized != bare else model_id
    if model_id in ("gemini-3-pro", "gemini-3-pro-preview"):
        return "gemini-3.1-pro-preview"
    if model_id == "gemini-3-flash":
        return "gemini-3-flash-preview"
    if model_id == "gemini-3.1-pro":
        return "gemini-3.1-pro-preview"
    # Gemini 3.1 Flash Lite graduated to GA on 2026-05-07; the -preview
    # endpoint is deprecated (shutdown 2026-05-25). Map to the stable GA id.
    if model_id == "gemini-3.1-flash-lite-preview":
        return "gemini-3.1-flash-lite"
    if model_id in ("gemini-3.1-flash", "gemini-3.1-flash-preview"):
        return "gemini-3-flash-preview"
    if model_id == "gemma-4-26b":
        return "gemma-4-26b-a4b-it"
    return model_id


def normalize_together_model_id(model_id: str) -> str:
    """Map renamed Together models to their current id."""
    if model_id == "moonshotai/Kimi-K2.5":
        return "moonshotai/Kimi-K2.6"
    return model_id


def normalize_antigravity_preview_model_id(model_id: str) -> str:
    """Append the ``-low`` effort suffix to bare Antigravity pro ids."""
    return f"{model_id}-low" if model_id in _ANTIGRAVITY_BARE_PRO_IDS else model_id


__all__ = [
    "normalize_antigravity_preview_model_id",
    "normalize_google_preview_model_id",
    "normalize_together_model_id",
]
