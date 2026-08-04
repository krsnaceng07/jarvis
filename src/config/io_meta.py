"""jarvis.config.io_meta — config metadata stamping (lastTouchedVersion, etc.).

OpenClaw parity: mirrors ``openclaw-main/src/config/io.meta.ts``.

Focused minimal port: stamps version metadata onto writes. The
``compute_model_policy_allowlist`` and
``has_model_policy_allowlist_migration_marker`` helpers are delegated
to caller-provided callables until the migration module lands.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Optional


#: Metadata keys automatically stamped on config writes.
AUTO_MANAGED_CONFIG_META_FIELDS = {
    "lastTouchedVersion": "lastTouchedVersion",
    "lastTouchedAt": "lastTouchedAt",
}


#: Config paths that hold auto-managed config metadata.
AUTO_MANAGED_CONFIG_META_PATHS = [
    ("meta", AUTO_MANAGED_CONFIG_META_FIELDS["lastTouchedVersion"]),
    ("meta", AUTO_MANAGED_CONFIG_META_FIELDS["lastTouchedAt"]),
]


def _is_record(value) -> bool:
    return isinstance(value, dict) and not isinstance(value, (list, tuple, str, bytes, set))


def stamp_config_write_metadata(
    cfg: Any,
    now: Optional[str] = None,
    version: Optional[str] = None,
    previous_config: Any = None,
    *,
    compute_model_policy_allowlist_fn: Optional[Callable] = None,
    has_model_policy_allowlist_migration_marker_fn: Optional[Callable] = None,
    is_explicit_model_policy_fn: Optional[Callable] = None,
) -> dict:
    """Stamp ``lastTouchedVersion`` and ``lastTouchedAt`` onto a config write.

    Mirrors :func:`stampConfigWriteMetadata`
    (``shared/config/io.meta.ts`).
    """
    if not isinstance(cfg, dict):
        cfg = {}
    version_str = version if version is not None else os.environ.get("OPENCLAW_VERSION", "0.0.0")
    now_str = now or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    # The migration-stamp side-effect is best-effort: when the
    # migration helpers are not wired, fall through to the simple stamp.
    if previous_config is not None and (
        callable(compute_model_policy_allowlist_fn)
        and callable(has_model_policy_allowlist_migration_marker_fn)
        and callable(is_explicit_model_policy_fn)
    ):
        defaults = ((cfg.get("agents") or {}).get("defaults")) if _is_record(cfg.get("agents")) else None
        default_allow = compute_model_policy_allowlist_fn({
            "root": cfg,
            "defaults": defaults,
        })
        if default_allow:
            existing_policy = (defaults or {}).get("modelPolicy") or {}
            cfg = {
                **cfg,
                "agents": {
                    **cfg.get("agents", {}),
                    "defaults": {
                        **(defaults or {}),
                        "modelPolicy": {
                            **existing_policy,
                            "allow": default_allow,
                        },
                    },
                },
                "meta": {
                    **cfg.get("meta", {}),
                    "migrations": {
                        **((cfg.get("meta") or {}).get("migrations") or {}),
                        "modelPolicyAllowlist": True,
                    },
                },
            }
        elif not has_model_policy_allowlist_migration_marker_fn(cfg):
            cfg = {
                **cfg,
                "meta": {
                    **cfg.get("meta", {}),
                    "migrations": {
                        **((cfg.get("meta") or {}).get("migrations") or {}),
                        "modelPolicyAllowlist": True,
                    },
                },
            }
    return {
        **cfg,
        "meta": {
            **cfg.get("meta", {}),
            AUTO_MANAGED_CONFIG_META_FIELDS["lastTouchedVersion"]: version_str,
            AUTO_MANAGED_CONFIG_META_FIELDS["lastTouchedAt"]: now_str,
        },
    }


__all__ = [
    "AUTO_MANAGED_CONFIG_META_FIELDS",
    "AUTO_MANAGED_CONFIG_META_PATHS",
    "stamp_config_write_metadata",
]
