"""jarvis.config.zod_schema_cloud_workers — cloud worker config Zod schemas.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.cloud-workers.ts``.
"""
from __future__ import annotations

from typing import Any, Optional


def is_plugin_json_value(value) -> bool:
    """Best-effort check that ``value`` is bounded finite JSON (dict/list/primitive)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, (list, tuple)):
        return all(is_plugin_json_value(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and is_plugin_json_value(v) for k, v in value.items())
    return False


def validate_cloud_worker_profile_settings(value) -> Optional[str]:
    """Validate that worker profile settings only use SecretRef for sensitive keys.

    Mirrors :func:`validateCloudWorkerProfileSettings`
    (``shared/config/zod-schema.cloud-workers.ts`).
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return None
    if isinstance(value, (list, tuple)):
        for entry in value:
            err = validate_cloud_worker_profile_settings(entry)
            if err is not None:
                return err
        return None
    if not isinstance(value, dict):
        return None
    if not is_plugin_json_value(value):
        return "Worker profile settings must be bounded finite JSON"
    for key, child in value.items():
        if not isinstance(key, str):
            return "Worker profile keys must be strings"
        base_key = key[:-3] if key.lower().endswith("ref") else key
        is_sensitive = (
            key.lower() == "keyref"
            or _key_looks_sensitive(key)
            or (base_key != key and _key_looks_sensitive(base_key))
        )
        if is_sensitive:
            if not _looks_like_secret_ref(child):
                return f"Worker profile {key} must use a SecretRef"
            continue
        err = validate_cloud_worker_profile_settings(child)
        if err is not None:
            return err
    return None


def _key_looks_sensitive(key: str) -> bool:
    """Mirrors ``is_sensitive_config_path`` semantics for the keys we care about."""
    if not isinstance(key, str):
        return False
    lower = key.lower()
    if lower.endswith("token") or "password" in lower or "secret" in lower:
        return True
    if "api" in lower and "key" in lower:
        return True
    return False


def _looks_like_secret_ref(value) -> bool:
    """Best-effort check for SecretRef-shaped values: ``{source, id}`` or
    inline string ``"${ENV_VAR}"``."""
    if isinstance(value, str):
        v = value.strip()
        return v.startswith("${") and v.endswith("}")
    if isinstance(value, dict):
        return isinstance(value.get("source"), str) and isinstance(value.get("id"), str)
    return False


#: CloudWorker profile settings schema (zod facade).
CloudWorkerSettingsSchema: Any = None  # z.record(z.string(), z.unknown()).superRefine(...)

#: CloudWorker profile schema.
CloudWorkerProfileSchema: Any = None  # z.object({...}).strict()

#: Top-level CloudWorkers config schema.
CloudWorkersConfigSchema: Any = None  # z.object({...}).strict().optional()


__all__ = [
    "is_plugin_json_value",
    "validate_cloud_worker_profile_settings",
    "CloudWorkerSettingsSchema",
    "CloudWorkerProfileSchema",
    "CloudWorkersConfigSchema",
]
