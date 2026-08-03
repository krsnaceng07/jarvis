"""jarvis.shared.model_key — canonical provider/model key.

OpenClaw parity: mirrors ``openclaw-main/src/shared/model-key.ts``.
"""
from __future__ import annotations


def model_key(provider: str, model: str) -> str:
    """Join provider and model into the canonical provider/model key.

    Mirrors :func:`modelKey` (``shared/model-key.ts``).
    """
    provider_id = (provider or "").strip()
    model_id = (model or "").strip()
    if not provider_id:
        return model_id
    if not model_id:
        return provider_id
    if model_id.lower().startswith(f"{provider_id.lower()}/"):
        return model_id
    return f"{provider_id}/{model_id}"


__all__ = ["model_key"]
