"""jarvis.plugins — Plugin registry + registrars.

OpenClaw parity: mirrors ``src/plugins/`` (registry.ts +
registry-types.ts + registry-empty.ts + registry-lifecycle.ts
+ registry-state.ts + registry-registrars.ts + registry-refresh.ts).
"""
from __future__ import annotations

from .empty import create_empty_plugin_registry  # noqa: F401
from .lifecycle import (  # noqa: F401
    is_plugin_registry_activated,
    is_plugin_registry_retired,
    mark_plugin_registry_active,
    mark_plugin_registry_retired,
)
from .refresh import (  # noqa: F401
    PluginRegistryRefreshLogger,
    invalidate_plugin_runtime_discovery_after_config_mutations,
    refresh_plugin_registry_after_config_mutations,
)
from .registrars import (  # noqa: F401
    PluginRegistrars,
    create_plugin_registrars,
)
from .state import (  # noqa: F401
    PluginRegistrationCapabilities,
    PluginRegistrationMode,
    PluginSideEffectGuard,
    PluginTypedHookPolicy,
    create_plugin_registry_state,
    resolve_plugin_registration_capabilities,
    resolve_typed_hook_timeout_ms,
)
from .types import (  # noqa: F401
    PluginChannelRegistration,
    PluginCommandRegistration,
    PluginHttpRouteRegistration,
    PluginNodeHostCommandRegistration,
    PluginRecord,
    PluginRegistry,
    PluginRegistryParams,
    PluginServiceRegistration,
    PluginSessionActionRegistryRegistration,
    PluginTextTransformsRegistration,
    PluginTrustedToolPolicyRegistryRegistration,
)
from .registry import (  # noqa: F401
    create_plugin_registry,
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
    "PluginChannelRegistration",
    "PluginCommandRegistration",
    "PluginHttpRouteRegistration",
    "PluginNodeHostCommandRegistration",
    "PluginServiceRegistration",
    "PluginSessionActionRegistryRegistration",
    "PluginTextTransformsRegistration",
    "PluginTrustedToolPolicyRegistryRegistration",
]
