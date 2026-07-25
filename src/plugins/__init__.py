"""jarvis.plugins — Plugin registry + registrars.

OpenClaw parity: mirrors ``src/plugins/`` (registry.ts +
registry-types.ts + registry-empty.ts + registry-lifecycle.ts
+ registry-state.ts + registry-registrars.ts + registry-refresh.ts).

Re-export shim: a follow-up phase will physically move
the 7 ``jarvis_sdk.plugin_registry_*`` modules here and
update all import sites.
"""
from __future__ import annotations

from jarvis_sdk.plugin_registry import (  # noqa: F401
    create_plugin_registry,
    PluginRecord,
    PluginRegistry,
    PluginRegistryParams,
)
from jarvis_sdk.plugin_registry_empty import create_empty_plugin_registry  # noqa: F401
from jarvis_sdk.plugin_registry_lifecycle import (  # noqa: F401
    is_plugin_registry_activated,
    is_plugin_registry_retired,
    mark_plugin_registry_active,
    mark_plugin_registry_retired,
)
from jarvis_sdk.plugin_registry_state import (  # noqa: F401
    PluginRegistrationCapabilities,
    PluginRegistrationMode,
    PluginSideEffectGuard,
    PluginTypedHookPolicy,
    create_plugin_registry_state,
    resolve_plugin_registration_capabilities,
    resolve_typed_hook_timeout_ms,
)
from jarvis_sdk.plugin_registry_registrars import (  # noqa: F401
    PluginRegistrars,
    create_plugin_registrars,
)
from jarvis_sdk.plugin_registry_refresh import (  # noqa: F401
    PluginRegistryRefreshLogger,
    invalidate_plugin_runtime_discovery_after_config_mutations,
    refresh_plugin_registry_after_config_mutations,
)

__all__ = [
    "create_plugin_registry",
    "create_empty_plugin_registry",
    "create_plugin_registry_state",
    "create_plugin_registrars",
    "is_plugin_registry_activated",
    "is_plugin_registry_retired",
    "mark_plugin_registry_active",
    "mark_plugin_registry_retired",
    "resolve_plugin_registration_capabilities",
    "resolve_typed_hook_timeout_ms",
    "refresh_plugin_registry_after_config_mutations",
    "invalidate_plugin_runtime_discovery_after_config_mutations",
    "PluginRecord",
    "PluginRegistry",
    "PluginRegistryParams",
    "PluginRegistrationCapabilities",
    "PluginRegistrationMode",
    "PluginSideEffectGuard",
    "PluginTypedHookPolicy",
    "PluginRegistrars",
    "PluginRegistryRefreshLogger",
]
