"""jarvis.config.plugin_auto_enable — public facade for plugin auto-enable.

OpenClaw parity: mirrors ``openclaw-main/src/config/plugin-auto-enable.ts``.

Focused minimal port: thin facade re-exporting the public surface.
Heavy lifting is delegated to ``plugin_auto_enable_apply``,
``plugin_auto_enable_detect``, and ``plugin_auto_enable_types``.
"""
from __future__ import annotations

# Re-exports keep the public surface stable.
from src.config.plugin_auto_enable_detect import detect_plugin_auto_enable_candidates  # noqa: F401
from src.config.plugin_auto_enable_types import (  # noqa: F401
    PluginAutoEnableCandidate,
    PluginAutoEnableResult,
)


# Thin delegations keep the stable facade API working while the full
# runtime-backed implementation is installed by the runtime layer.
def apply_plugin_auto_enable(*args, **kwargs):  # pragma: no cover
    from src.config.plugin_auto_enable_apply import apply_plugin_auto_enable as _impl

    params = args[0] if args and isinstance(args[0], dict) else kwargs
    if not isinstance(params, dict) or "config" not in params:
        raise NotImplementedError("applyPluginAutoEnable facade — install via runtime hooks")
    return _impl(params)


def materialize_plugin_auto_enable_candidates(*args, **kwargs):  # pragma: no cover
    from src.config.plugin_auto_enable_apply import apply_plugin_auto_enable as _impl

    params = args[0] if args and isinstance(args[0], dict) else kwargs
    return _impl(params).get("config") if isinstance(params, dict) else None


def resolve_plugin_auto_enable_candidate_reason(*args, **kwargs):  # pragma: no cover
    if args and isinstance(args[0], dict):
        candidate = args[0]
    else:
        candidate = kwargs.get("candidate") or {}
    return candidate.get("kind") or "auto-enabled"


__all__ = [
    "detect_plugin_auto_enable_candidates",
    "apply_plugin_auto_enable",
    "materialize_plugin_auto_enable_candidates",
    "resolve_plugin_auto_enable_candidate_reason",
    "PluginAutoEnableCandidate",
    "PluginAutoEnableResult",
]
