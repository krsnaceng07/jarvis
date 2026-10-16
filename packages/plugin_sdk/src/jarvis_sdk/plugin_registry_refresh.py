"""jarvis_sdk.plugin_registry_refresh — refresh helper (STUB).

OpenClaw parity: mirrors ``src/plugins/registry-refresh.ts``
(~65 LOC).
Refreshes the persisted plugin registry and clears the
runtime discovery cache after a config mutation. This
module is a **minimal stub** for Phase 5.6a — the full
port requires the ``installed-plugin-index``,
``plugin-lifecycle-trace``, ``plugin-registry``, and
``loader`` modules (all in OpenClaw's ``src/plugins/``).
A later phase will port those modules and replace this
stub.

What works today (Phase 5.6a):
- ``PluginRegistryRefreshLogger`` TypedDict.
- ``refresh_plugin_registry_after_config_mutations``
  (matches the OpenClaw name) — emits a warning via
  the optional ``logger.warn`` and returns. The full
  implementation will load install records, call
  ``refreshPluginRegistry``, and invalidate the
  runtime cache.
- ``invalidate_plugin_runtime_discovery_after_config_mutations``
  — emits a warning and returns. The full
  implementation calls
  ``clearPluginRegistryLoadCache`` from ``loader.ts``.

The Python port uses the same name-shape as the source
so call sites can be wired up cleanly when the
follow-up phase lands.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypedDict

from .memory_host_error_utils import format_error_message

if TYPE_CHECKING:
    pass


class PluginRegistryRefreshLogger(TypedDict, total=False):
    """Optional warning sink for refresh failures.

    Mirrors OpenClaw's ``PluginRegistryRefreshLogger``.
    """

    warn: Any  # (message: str) -> None


# Default logger used when the caller does not pass one.
_default_logger = logging.getLogger("jarvis_sdk.plugin_registry_refresh")


async def refresh_plugin_registry_after_config_mutations(
    params: dict[str, Any],
) -> None:
    """Refresh persisted registry and clear runtime discovery cache.

    Mirrors OpenClaw's ``refreshPluginRegistryAfterConfigMutation``.
    The Python port of Phase 5.6a is a **stub**: it logs a
    warning via the optional ``logger.warn`` and returns.
    The full implementation (load install records +
    call ``refreshPluginRegistry`` + invalidate the
    runtime cache) is deferred to a later phase.
    """
    logger = params.get("logger") or _default_logger
    reason = params.get("reason", "unknown")
    try:
        # Full implementation will:
        # 1. Load install records via ``loadInstalledPluginIndexInstallRecords``
        # 2. Trace + call ``refreshPluginRegistry`` from ``plugin-registry.ts``
        # 3. Invalidate the runtime discovery cache
        # For now we just acknowledge the request.
        _ = reason
        return
    except Exception as error:  # noqa: BLE001 — match OpenClaw catch-all
        message = f"Plugin registry refresh failed: {format_error_message(error)}"
        if logger is not None and isinstance(logger, logging.Logger):
            logger.warning(message)
        elif callable(getattr(logger, "warn", None)):
            logger.warn(message)  # type: ignore[union-attr]


async def invalidate_plugin_runtime_discovery_after_config_mutations(
    params: dict[str, Any],
) -> None:
    """Invalidate the runtime discovery cache after a config mutation.

    Mirrors OpenClaw's ``invalidatePluginRuntimeDiscoveryAfterConfigMutation``.
    The Python port of Phase 5.6a is a **stub**: it logs
    a warning and returns. The full implementation calls
    ``clearPluginRegistryLoadCache`` from ``loader.ts``.
    """
    logger = params.get("logger") or _default_logger
    try:
        # Full implementation will:
        # 1. ``await import("./loader.js")``
        # 2. ``clearPluginRegistryLoadCache()``
        return
    except Exception as error:  # noqa: BLE001
        message = f"Plugin runtime cache invalidation failed: {format_error_message(error)}"
        if logger is not None and isinstance(logger, logging.Logger):
            logger.warning(message)
        elif callable(getattr(logger, "warn", None)):
            logger.warn(message)  # type: ignore[union-attr]


__all__ = [
    "PluginRegistryRefreshLogger",
    "refresh_plugin_registry_after_config_mutations",
    "invalidate_plugin_runtime_discovery_after_config_mutations",
]
