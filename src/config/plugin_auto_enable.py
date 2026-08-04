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


# Placeholder facades for the apply + materialize + reason-resolution
# helpers until the corresponding ``plugin-auto-enable.apply`` and
# ``plugin-auto-enable.shared`` modules land.
def apply_plugin_auto_enable(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("applyPluginAutoEnable facade — install via runtime hooks")


def materialize_plugin_auto_enable_candidates(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("materializePluginAutoEnableCandidates facade")


def resolve_plugin_auto_enable_candidate_reason(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("resolvePluginAutoEnableCandidateReason facade")


__all__ = [
    "detect_plugin_auto_enable_candidates",
    "apply_plugin_auto_enable",
    "materialize_plugin_auto_enable_candidates",
    "resolve_plugin_auto_enable_candidate_reason",
    "PluginAutoEnableCandidate",
    "PluginAutoEnableResult",
]
