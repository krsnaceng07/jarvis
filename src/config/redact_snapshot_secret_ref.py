"""jarvis.config.redact_snapshot_secret_ref — SecretRef-shape redaction helpers.

OpenClaw parity: mirrors
``openclaw-main/src/config/redact-snapshot.secret-ref.ts``.
"""
from __future__ import annotations

from typing import Callable


def is_secret_ref_shape(value) -> bool:
    """Return whether ``value`` is a SecretRef-shaped dict with source+id.

    Mirrors :func:`isSecretRefShape`
    (``shared/config/redact-snapshot.secret-ref.ts`).
    """
    if not isinstance(value, dict):
        return False
    return isinstance(value.get("source"), str) and isinstance(value.get("id"), str)


def redact_secret_ref_id(params: dict) -> dict:
    """Redact a SecretRef id while preserving non-secret structural fields.

    Mirrors :func:`redactSecretRefId`
    (``shared/config/redact-snapshot.secret-ref.ts`).
    """
    value = params.get("value") or {}
    values_list = params.get("values")
    sentinel: str = params.get("redactedSentinel") or "***"
    is_env_placeholder: Callable[[str], bool] = params.get("isEnvVarPlaceholder") or (lambda v: False)
    if not isinstance(value, dict):
        return dict(value)
    redacted = dict(value)
    sid = value.get("id")
    if isinstance(sid, str) and not is_env_placeholder(sid):
        # Concrete ids (not ${ENV_VAR} placeholders) are collected for raw
        # replacement; the structured shape keeps the sentinel.
        if isinstance(values_list, list):
            values_list.append(sid)
        redacted["id"] = sentinel
    return redacted


__all__ = [
    "is_secret_ref_shape",
    "redact_secret_ref_id",
]
