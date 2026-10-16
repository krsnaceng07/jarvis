"""jarvis_sdk.plugin_registry_lifecycle — active/retired registry tracking.

OpenClaw parity: mirrors
``src/plugins/registry-lifecycle.ts`` (30 LOC).
Tracks active and retired plugin registries so stale
runtime calls can be rejected.

Public API:
- ``mark_plugin_registry_retired(registry)`` — mark a
  registry as retired (no-op on ``None``).
- ``mark_plugin_registry_active(registry)`` — mark a
  registry as active and clear any previous retired state.
- ``is_plugin_registry_activated(registry)`` — true when
  the registry has been activated.
- ``is_plugin_registry_retired(registry)`` — true when
  the registry has been retired by a newer active one.

Key port decisions:
- OpenClaw uses ``WeakSet<PluginRegistry>`` because JS
  objects are always heap-allocated; the Python stdlib
  ``weakref`` module does NOT support weak references
  to ``dict`` instances. The Python port uses a regular
  ``set`` keyed on ``id(registry)`` instead — the
  active/retired flags are process-wide singletons, and
  identity-based lookup matches the OpenClaw semantics
  (same object registered, same object queried). When a
  registry is garbage-collected, its ``id`` may be reused
  for a future registry, but that's a minor issue since
  the lifecycle flags are advisory, not authoritative.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .plugin_registry_types import PluginRegistry

# Process-wide singleton sets keyed on ``id(registry)``.
# Mirrors OpenClaw's ``WeakSet`` semantics for the active
# and retired flags. The Python port uses ``id()`` keys
# because ``dict`` instances can't be weak-referenced.
_retired_registries: set[int] = set()
_activated_registries: set[int] = set()


def mark_plugin_registry_retired(
    registry: PluginRegistry | None,
) -> None:
    """Mark ``registry`` retired so late runtime calls can reject it.

    Mirrors OpenClaw's ``markPluginRegistryRetired``. No-op
    when ``registry`` is ``None`` (matches the source's
    ``if (registry)`` guard).
    """
    if registry is not None:
        _retired_registries.add(id(registry))


def mark_plugin_registry_active(
    registry: PluginRegistry | None,
) -> None:
    """Mark ``registry`` active and clear any previous retired state.

    Mirrors OpenClaw's ``markPluginRegistryActive``.
    No-op when ``registry`` is ``None``.
    """
    if registry is not None:
        _activated_registries.add(id(registry))
        _retired_registries.discard(id(registry))


def is_plugin_registry_activated(registry: PluginRegistry) -> bool:
    """True when ``registry`` has been activated for runtime use.

    Mirrors OpenClaw's ``isPluginRegistryActivated``.
    """
    return id(registry) in _activated_registries


def is_plugin_registry_retired(registry: PluginRegistry) -> bool:
    """True when ``registry`` has been retired by a newer active one.

    Mirrors OpenClaw's ``isPluginRegistryRetired``.
    """
    return id(registry) in _retired_registries


__all__ = [
    "mark_plugin_registry_retired",
    "mark_plugin_registry_active",
    "is_plugin_registry_activated",
    "is_plugin_registry_retired",
]
