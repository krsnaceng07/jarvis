"""Host runtime installer helpers.

Provides a tiny `install_host_runtime` helper that creates the
plugin registry and optionally installs runtime hooks into the
config IO facade. This helps host entrypoints wire the runtime
without scattering startup plumbing across the codebase.
"""
from __future__ import annotations

from typing import Any, Dict, cast

from .registry import create_plugin_registry
from .types import PluginRegistryParams
from src.config.io import install_runtime_hooks


def install_host_runtime(registry_params: Dict[str, Any] | None = None, runtime_hooks: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Create and return the plugin registry and install runtime hooks.

    Args:
        registry_params: Passed to `create_plugin_registry` (optional).
        runtime_hooks: A map of hook name -> callable to install via
            `src.config.io.install_runtime_hooks` (optional).

    Returns:
        The plugin registry dict returned by `create_plugin_registry`.
    """
    params = registry_params or {}
    # Host callers pass plain dicts; the registry only reads known
    # optional keys (TypedDict total=False), so this cast is shape-safe.
    registry = create_plugin_registry(cast(PluginRegistryParams, params))
    if isinstance(runtime_hooks, dict):
        try:
            install_runtime_hooks(runtime_hooks)
        except Exception:
            # Be conservative: do not fail startup if hooks are invalid.
            pass
    try:
        from jarvis_sdk.api import (  # noqa: PLC0415
            set_host_effective_agent_runtime_resolver,
            set_host_thinking_policy_resolver,
        )
        from src.agents.harness.selection import (  # noqa: PLC0415
            resolve_host_effective_agent_runtime,
        )
        from src.plugins.provider_thinking import (  # noqa: PLC0415
            resolve_host_thinking_policy,
        )

        # Host-side agent defaults for api.runtime.agent consumers
        # (e.g. llm-task thinking validation + harness override).
        # Provider-owned profiles (today: OpenAI) answer thinking;
        # anything else keeps local heuristics.
        set_host_thinking_policy_resolver(resolve_host_thinking_policy)
        set_host_effective_agent_runtime_resolver(resolve_host_effective_agent_runtime)
    except Exception:
        # Be conservative: agent defaults stay on their fallbacks
        # when the host surface cannot load.
        pass
    return registry


__all__ = ["install_host_runtime"]
