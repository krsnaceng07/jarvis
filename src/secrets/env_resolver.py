"""Secret reference resolver — mirrors OpenClaw secret interpolation."""

from __future__ import annotations

import os
from .store import GLOBAL_SECRETS_STORE, SecretsStore


def resolve_secret_ref(ref: str, store: SecretsStore | None = None) -> str:
    """Resolve `$JARVIS_SECRET:<key>` pattern or return string unchanged."""
    if not isinstance(ref, str):
        return ref

    sec_store = store or GLOBAL_SECRETS_STORE

    prefix = "$JARVIS_SECRET:"
    if ref.startswith(prefix):
        key = ref[len(prefix) :].strip()
        val = sec_store.get_secret(key) or os.environ.get(key, "")
        return val

    return ref


__all__ = ["resolve_secret_ref"]
