from __future__ import annotations

from src.plugins.active_runtime_registry import get_loaded_runtime_plugin_registry
from src.plugins.provider_thinking import resolve_provider_thinking_profile
from src.plugins.runtime_state_key import set_plugin_registry_state
from src.plugins.standalone_runtime_registry_loader import (
    ensure_standalone_runtime_plugin_registry_loaded,
)


def test_active_runtime_registry_resolves_provider_thinking_profile() -> None:
    set_plugin_registry_state(
        {
            "activeRegistry": {
                "providers": [
                    {
                        "provider": {
                            "id": "demo-provider",
                            "aliases": ["demo"],
                            "resolveThinkingProfile": lambda context: {
                                "provider": "demo-provider",
                                "level": "xhigh",
                                "context": context,
                            },
                        }
                    }
                ]
            }
        }
    )

    profile = resolve_provider_thinking_profile(
        {"provider": "demo", "context": {"modelId": "gpt-5.4"}}
    )

    assert profile is not None
    assert profile["provider"] == "demo-provider"
    assert profile["level"] == "xhigh"


def test_loaded_runtime_registry_loader_reuses_state_and_required_plugins() -> None:
    set_plugin_registry_state(
        {
            "activeRegistry": {
                "providers": [{"provider": {"id": "memory-core"}}],
                "pluginIds": ["memory-core"],
            }
        }
    )

    loaded = get_loaded_runtime_plugin_registry({"requiredPluginIds": ["memory-core"]})
    assert loaded is not None
    assert loaded["activeRegistry"]["pluginIds"] == ["memory-core"]

    loader_state = ensure_standalone_runtime_plugin_registry_loaded(
        {"requiredPluginIds": ["memory-core"]}
    )
    assert loader_state is not None
    assert loader_state["activeRegistry"]["pluginIds"] == ["memory-core"]
