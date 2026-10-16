"""jarvis.config.plugin_auto_enable_detect — detect plugin auto-enable candidates.

OpenClaw parity: mirrors
``openclaw-main/src/config/plugin-auto-enable.detect.ts``.

Focused minimal port: the readiness check, manifest-registry resolver,
and candidate resolver are delegated to caller-provided callables.
"""
from __future__ import annotations

import os
from typing import Any, Optional



def detect_plugin_auto_enable_candidates(
    *,
    config: Optional[Any] = None,
    env: Optional[dict] = None,
    manifest_registry: Any = None,
    discovery: Any = None,
    resolve_plugin_auto_enable_readiness_fn=None,
    resolve_plugin_auto_enable_manifest_registry_fn=None,
    resolve_configured_plugin_auto_enable_candidates_fn=None,
) -> list:
    """Detect installed plugins that should become enabled from existing config usage.

    Mirrors :func:`detectPluginAutoEnableCandidates`
    (``shared/config/plugin-auto-enable.detect.ts`).
    """
    env = env if env is not None else dict(os.environ)
    config = config if config is not None else {}
    if not callable(resolve_plugin_auto_enable_readiness_fn):
        return []
    readiness = resolve_plugin_auto_enable_readiness_fn(config, env, discovery)
    if not readiness.get("mayNeedAutoEnable"):
        return []
    if not callable(resolve_plugin_auto_enable_manifest_registry_fn):
        return []
    registry = resolve_plugin_auto_enable_manifest_registry_fn({
        "config": config,
        "env": env,
        "manifestRegistry": manifest_registry,
    })
    if not callable(resolve_configured_plugin_auto_enable_candidates_fn):
        return []
    return list(resolve_configured_plugin_auto_enable_candidates_fn({
        "config": config,
        "env": env,
        "registry": registry,
        "configuredChannelIds": readiness.get("configuredChannelIds", []),
    }) or [])


__all__ = ["detect_plugin_auto_enable_candidates"]
