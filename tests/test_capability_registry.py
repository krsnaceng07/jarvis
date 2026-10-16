"""Tests for src/plugins/capability_registry.py.

Mirrors tests of docs/plugins/capability-model.md in OpenClaw.
"""

from __future__ import annotations


from src.plugins.capability_registry import CapabilityRegistry


def test_capability_registry_embedding():
    reg_sys = CapabilityRegistry()
    reg = reg_sys.register_embedding_provider(
        plugin_id="acme-ai",
        id="acme-embed",
        config={"label": "Acme Embeddings", "dimensions": 1536},
    )
    assert reg.capability_type == "embedding"
    assert reg.id == "acme-embed"
    assert reg.label == "Acme Embeddings"
    assert "acme-embed" in reg_sys.embedding_providers


def test_capability_registry_image_gen():
    reg_sys = CapabilityRegistry()
    reg = reg_sys.register_image_generation_provider(
        plugin_id="openai-provider",
        id="dall-e-3",
        config={"label": "DALL-E 3"},
    )
    assert reg.capability_type == "image_generation"
    assert reg.id == "dall-e-3"
    assert "dall-e-3" in reg_sys.image_generation_providers


def test_capability_registry_web_search():
    reg_sys = CapabilityRegistry()
    reg = reg_sys.register_web_search_provider(
        plugin_id="acme-search-plugin",
        id="acme-search",
        config={"label": "Acme Search"},
    )
    assert reg.capability_type == "web_search"
    assert reg.id == "acme-search"
    assert "acme-search" in reg_sys.web_search_providers
