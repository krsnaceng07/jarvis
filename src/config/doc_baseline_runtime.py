"""jarvis.config.doc_baseline_runtime — runtime facade for docs baseline generation.

OpenClaw parity: mirrors ``openclaw-main/src/config/doc-baseline.runtime.ts``.
"""
from __future__ import annotations

from typing import Any, Callable


def _load_plugin_manifest_registry(*args, **kwargs) -> Any:
    """Focused minimal stub for plugin manifest registry loading.

    The full implementation is wired as the plugins/manifest-registry
    port lands.
    """
    raise NotImplementedError("load_plugin_manifest_registry: wire as plugins/manifest-registry lands")


def _collect_bundled_channel_configs(*args, **kwargs) -> Any:
    raise NotImplementedError("collect_bundled_channel_configs: wire as plugins/bundled-channel-config-metadata lands")


def _collect_channel_schema_metadata(*args, **kwargs) -> Any:
    raise NotImplementedError("collect_channel_schema_metadata: wire as config/channel-config-metadata lands")


def _collect_plugin_schema_metadata(*args, **kwargs) -> Any:
    raise NotImplementedError("collect_plugin_schema_metadata: wire as config/channel-config-metadata lands")


def _build_config_schema(*args, **kwargs) -> Any:
    raise NotImplementedError("build_config_schema: wire as config/schema lands")


load_plugin_manifest_registry: Callable = _load_plugin_manifest_registry
collect_bundled_channel_configs: Callable = _collect_bundled_channel_configs
collect_channel_schema_metadata: Callable = _collect_channel_schema_metadata
collect_plugin_schema_metadata: Callable = _collect_plugin_schema_metadata
build_config_schema: Callable = _build_config_schema


__all__ = [
    "load_plugin_manifest_registry",
    "collect_bundled_channel_configs",
    "collect_channel_schema_metadata",
    "collect_plugin_schema_metadata",
    "build_config_schema",
]
