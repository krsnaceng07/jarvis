"""define_plugin_entry — the entry shape every plugin returns.

Mirrors OpenClaw's ``definePluginEntry`` from
``src/plugin-sdk/plugin-entry.ts``. The shape is:

    {
        id: str,
        kind: "channel" | "provider" | "tool" | ...,
        name: str,
        description: str,
        version: str,
        activation: "always" | "on_startup" | "on_demand",
        requires: list[str],
        permissions: list[str],
        register: (api) -> None,
    }

A plugin's ``__init__.py`` exports ``entry = define_plugin_entry(...)`` and
the host imports it.

The ``register(api)`` callback is where the plugin does all its work:
calls ``api.register_tool(...)``, ``api.register_command(...)``, etc.
The host invokes ``register`` exactly once during activation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from .api import PluginApi
    from .manifest import PluginActivation, PluginKind


@dataclass
class PluginEntry:
    """The shape every JARVIS plugin returns from its entry module.

    Mirrors OpenClaw's plugin-entry pattern. Created by
    ``define_plugin_entry(...)``; the host reads these fields to decide
    when to load the plugin and what to do during activation.
    """

    id: str
    kind: PluginKind
    name: str
    description: str
    register: Callable[[PluginApi], None]
    version: str = "0.1.0"
    activation: PluginActivation = "on_demand"
    requires: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)


def define_plugin_entry(
    id: str,
    kind: PluginKind,
    name: str,
    description: str,
    register: Callable[[PluginApi], None],
    *,
    version: str = "0.1.0",
    activation: PluginActivation = "on_demand",
    requires: list[str] | None = None,
    permissions: list[str] | None = None,
) -> PluginEntry:
    """Define a plugin entry. Mirrors OpenClaw's ``definePluginEntry``.

    Parameters
    ----------
    id : str
        Stable plugin id (matches the directory name in ``extensions/``).
        Snake-case (e.g. ``"tool_weather"``, ``"memory_core"``).
    kind : str
        One of ``"channel" | "provider" | "tool" | "memory" | "skill" | "infra" | "migration"``.
    name : str
        Human-readable display name.
    description : str
        One-line description used in plugin lists, ``jarvis extensions list``,
        and the docs site.
    register : Callable
        Function called once during activation. Receives a ``PluginApi``
        and uses its methods to register tools / commands / etc.
    version : str
        Semver version of the plugin.
    activation : str
        When the host should load the plugin. ``"on_demand"`` (default) means
        only when something explicitly references it; ``"on_startup"`` means
        always at host start; ``"always"`` means even on passive/control paths.
    requires : list[str]
        Other plugin ids this plugin depends on. Loaded first.
    permissions : list[str]
        Permissions this plugin needs (e.g. ``"network:outbound"``).
        Enforced by ``jarvis doctor`` and the permission system.

    Returns
    -------
    PluginEntry
        The entry object. The host imports it; plugins don't need to
        use the return value.
    """
    return PluginEntry(
        id=id,
        kind=kind,
        name=name,
        description=description,
        register=register,
        version=version,
        activation=activation,
        requires=requires or [],
        permissions=permissions or [],
    )


__all__ = ["PluginEntry", "define_plugin_entry"]
