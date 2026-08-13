"""jarvis.plugins.runtime_state_key — process-global registry state key.

OpenClaw parity: mirrors
``openclaw-main/src/plugins/runtime-state-key.ts``.

Adaptations
-----------
- The OpenClaw source publishes a ``Symbol.for`` key on
  ``globalThis``. Python has no ``globalThis``; the port stores the
  registry state in a module-level holder keyed by the same string
  (``Symbol.for`` semantics — one shared slot per process).
"""
from __future__ import annotations

from typing import Any, Optional

#: Mirrors ``PLUGIN_REGISTRY_STATE = Symbol.for("openclaw.pluginRegistryState")``.
PLUGIN_REGISTRY_STATE = "openclaw.pluginRegistryState"

#: The process-global slot (``globalThis[PLUGIN_REGISTRY_STATE]``).
_GLOBAL_STATE: dict[str, Any] = {}


def get_plugin_registry_state() -> Optional[dict]:
    """Read ``globalThis[PLUGIN_REGISTRY_STATE]`` (or ``None``)."""
    return _GLOBAL_STATE.get(PLUGIN_REGISTRY_STATE)


def set_plugin_registry_state(state: Optional[dict]) -> None:
    """Write ``globalThis[PLUGIN_REGISTRY_STATE]`` (``None`` clears)."""
    if state is None:
        _GLOBAL_STATE.pop(PLUGIN_REGISTRY_STATE, None)
    else:
        _GLOBAL_STATE[PLUGIN_REGISTRY_STATE] = state


__all__ = [
    "PLUGIN_REGISTRY_STATE",
    "get_plugin_registry_state",
    "set_plugin_registry_state",
]
