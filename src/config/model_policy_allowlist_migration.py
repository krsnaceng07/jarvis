"""jarvis.config.model_policy_allowlist_migration — legacy model allowlist detection.

OpenClaw parity: mirrors
``openclaw-main/src/config/model-policy-allowlist-migration.ts``.
"""
from __future__ import annotations

from typing import Any, List, Optional


#: Marker key under ``meta.migrations`` that records the migration.
MODEL_POLICY_ALLOWLIST_MIGRATION_MARKER = "modelPolicyAllowlist"


def _is_record(value) -> bool:
    return isinstance(value, dict) and not isinstance(value, (list, tuple, str, bytes, set))


def has_model_policy_allowlist_migration_marker(value) -> bool:
    """Return whether ``value`` carries the modelPolicyAllowlist migration marker.

    Mirrors :func:`hasModelPolicyAllowlistMigrationMarker`
    (``shared/config/model-policy-allowlist-migration.ts`).
    """
    if not _is_record(value):
        return False
    meta = value.get("meta")
    if not _is_record(meta):
        return False
    migrations = meta.get("migrations")
    if not _is_record(migrations):
        return False
    return migrations.get(MODEL_POLICY_ALLOWLIST_MIGRATION_MARKER) is True


def is_explicit_model_policy(value) -> bool:
    """Return whether ``value`` is an explicit per-agent model policy object."""
    return _is_record(value)


def has_explicit_model_policy_allow(value) -> bool:
    """Return whether ``value`` is an explicit per-agent policy with its own ``allow``."""
    return is_explicit_model_policy(value) and "allow" in value


def compute_model_policy_allowlist(params: dict) -> Optional[List[str]]:
    """Return legacy allowlist refs for ``params.defaults`` when migration is unmarked.

    Mirrors :func:`computeModelPolicyAllowlist`
    (``shared/config/model-policy-allowlist-migration.ts`).
    """
    root = params.get("root")
    defaults = params.get("defaults")
    if has_model_policy_allowlist_migration_marker(root):
        return None
    return collect_legacy_default_model_allow_refs(defaults)


def collect_legacy_default_model_allow_refs(defaults) -> Optional[List[str]]:
    """Collect the legacy default model allowlist refs from ``defaults.models``."""
    if not _is_record(defaults):
        return None
    # An explicit modelPolicy object opts into the new semantics; sibling
    # models map is then metadata-only and never read as a legacy allowlist.
    if is_explicit_model_policy(defaults.get("modelPolicy")):
        return None
    models = defaults.get("models")
    if not _is_record(models):
        return None
    refs = [k for k in models.keys() if isinstance(k, str) and k.strip()]
    return refs or None


__all__ = [
    "MODEL_POLICY_ALLOWLIST_MIGRATION_MARKER",
    "has_model_policy_allowlist_migration_marker",
    "is_explicit_model_policy",
    "has_explicit_model_policy_allow",
    "compute_model_policy_allowlist",
    "collect_legacy_default_model_allow_refs",
]
