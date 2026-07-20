"""jarvis_sdk.plugin_config — live plugin config resolution.

OpenClaw parity: mirrors
``openclaw/plugin-sdk/plugin-config-runtime``'s
``resolveLivePluginConfigObject``.

Used by extensions that want their config to follow the
host's live config (the user can edit ``config/jarvis.json``
and the change should be visible on the next turn without a
restart). ``active-memory`` is the canonical consumer.

Architecture
============
The OpenClaw pattern is: a "live config" supplier is a
zero-arg callable that returns the most recent config.
The plugin's effective config is ``merge(plugin_static,
live_plugin_config)`` — static defaults + live overrides.

The Python port mirrors this with a small helper:
``resolve_live_plugin_config_object(live_config_supplier,
plugin_id, plugin_static_config)`` returns a merged dict.

Parity
======
- ``resolve_live_plugin_config_object(supplier, plugin_id, static)``
  → ``dict | None``. If the live config is unavailable
  (supplier returns None, or no ``plugins.entries.<id>``
  key), returns None. Otherwise returns the merged dict.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


# ruff: noqa: PLR0911
# Each early return handles a specific failure mode (no
# supplier, supplier raises, config malformed, plugin id
# missing, plugin config malformed). The returns make the
# failure surface explicit in the test suite.


def resolve_live_plugin_config_object(
    get_config: Callable[[], dict[str, Any] | None] | None,
    plugin_id: str,
    static_config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve the live plugin config, merged with static defaults.

    Mirrors ``openclaw/plugin-sdk/plugin-config-runtime``'s
    ``resolveLivePluginConfigObject``. Used by extensions
    that want to follow the host's live config (so a user
    editing ``config/jarvis.json`` sees the change without a
    restart).

    Returns ``None`` if no live config is available (caller
    should fall back to static). Otherwise returns a merged
    dict: live overrides win over static.
    """
    if get_config is None:
        return None
    try:
        live = get_config()
    except Exception:
        return None
    if not isinstance(live, dict):
        return None
    plugins = live.get("plugins") if isinstance(live.get("plugins"), dict) else None
    if not plugins:
        return None
    entries = plugins.get("entries") if isinstance(plugins.get("entries"), dict) else None
    if not isinstance(entries, dict):
        return None
    live_plugin = entries.get(plugin_id)
    if not isinstance(live_plugin, dict):
        return None

    # Merge: static first, then live overrides. Live wins.
    merged: dict[str, Any] = {}
    if isinstance(static_config, dict):
        merged.update(static_config)
    merged.update(live_plugin)
    return merged


__all__ = ["resolve_live_plugin_config_object"]
