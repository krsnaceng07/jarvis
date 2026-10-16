from __future__ import annotations

from src.plugins.capability_provider_runtime import (
    resolve_plugin_capability_provider,
    resolve_plugin_capability_providers,
)
from src.plugins.runtime_state_key import set_plugin_registry_state


def test_resolve_plugin_capability_providers_from_active_registry() -> None:
    set_plugin_registry_state(
        {
            "activeRegistry": {
                "providers": [
                    {
                        "provider": {
                            "id": "memory-ollama",
                            "kind": "memoryEmbeddingProvider",
                            "defaultModel": "llama3.1:8b",
                        }
                    }
                ]
            }
        }
    )

    providers = resolve_plugin_capability_providers({
        "key": "memoryEmbeddingProviders",
        "cfg": {},
    })

    assert [provider["id"] for provider in providers] == ["memory-ollama"]


def test_resolve_plugin_capability_provider_by_id() -> None:
    set_plugin_registry_state(
        {
            "activeRegistry": {
                "providers": [
                    {
                        "provider": {
                            "id": "vector-memory",
                            "aliases": ["memory-vector"],
                            "defaultModel": "nomic-embed-text",
                        }
                    }
                ]
            }
        }
    )

    provider = resolve_plugin_capability_provider({
        "key": "memoryEmbeddingProviders",
        "providerId": "memory-vector",
        "cfg": {},
    })

    assert provider is not None
    assert provider["id"] == "vector-memory"
