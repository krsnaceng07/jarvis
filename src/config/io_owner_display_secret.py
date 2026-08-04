"""jarvis.config.io_owner_display_secret — runtime-only owner display secret retention.

OpenClaw parity: mirrors
``openclaw-main/src/config/io.owner-display-secret.ts``.

Focused minimal port: the public surface retains generated secrets in a
shared runtime-state map keyed by config path so the config object's
identity is preserved.
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict


class OwnerDisplaySecretRuntimeState(TypedDict, total=False):
    """Runtime-only owner display secrets keyed by config path."""

    pendingByPath: dict


def retain_generated_owner_display_secret(params: dict) -> Any:
    """Retain a generated owner display secret in the runtime state without writing to disk.

    Mirrors :func:`retainGeneratedOwnerDisplaySecret`
    (``shared/config/io.owner-display-secret.ts`).
    """
    config = params.get("config")
    config_path = params.get("configPath") or ""
    generated_secret: Optional[str] = params.get("generatedSecret")
    state = params.get("state") or {"pendingByPath": {}}
    pending = state.setdefault("pendingByPath", {})
    if not generated_secret:
        # Clear stale pending secrets once the config load no longer generated one for this path.
        pending.pop(config_path, None)
        return config
    pending[config_path] = generated_secret
    return config


__all__ = [
    "OwnerDisplaySecretRuntimeState",
    "retain_generated_owner_display_secret",
]
