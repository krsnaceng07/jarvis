from __future__ import annotations

from typing import Any, Optional

from src.sessions.model_registry import get_credentials_for_model, get_auth_storage


def resolve_credentials(provider: str | None = None, model: str | None = None) -> Optional[Any]:
    """Central helper to resolve credentials for a provider or model.

    Precedence:
    - If `model` provided, attempt `get_credentials_for_model(model)`.
    - Otherwise, consult auth storage for provider-named credentials.
    - Returns None when no credentials found.
    """
    if model:
        cred = get_credentials_for_model(model)
        if cred is not None:
            return cred

    # Fallback to provider lookup in auth storage
    auth = get_auth_storage()
    if auth is None:
        return None
    return auth.get_credentials(provider) if provider else None


__all__ = ["resolve_credentials"]
