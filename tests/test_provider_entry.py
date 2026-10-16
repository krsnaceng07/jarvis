"""Tests for packages/plugin_sdk/src/jarvis_sdk/provider_entry.py.

Mirrors tests of src/plugin-sdk/provider-entry.ts in OpenClaw.
"""

from __future__ import annotations


from jarvis_sdk.plugin_entry import JarvisPluginApi
from jarvis_sdk.provider_entry import (
    create_provider_api_key_auth_method,
    define_single_provider_plugin_entry,
)


def test_create_provider_api_key_auth_method():
    auth = create_provider_api_key_auth_method(
        provider_id="acme-ai",
        method_id="api-key",
        label="Acme AI API key",
        env_var="ACME_AI_API_KEY",
        flag_name="--acme-ai-api-key",
        default_model="acme-ai/acme-large",
    )
    assert auth.providerId == "acme-ai"
    assert auth.methodId == "api-key"
    assert auth.envVar == "ACME_AI_API_KEY"
    assert auth.defaultModel == "acme-ai/acme-large"


def test_define_single_provider_plugin_entry():
    def build_prov(ctx):
        return {
            "baseUrl": "https://api.acme-ai.com/v1",
            "models": [{"id": "acme-large", "name": "Acme Large"}],
        }

    entry = define_single_provider_plugin_entry(
        id="acme-ai",
        name="Acme AI",
        description="Acme AI provider",
        provider_label="Acme AI",
        env_vars=["ACME_AI_API_KEY"],
        build_provider=build_prov,
    )

    assert entry.id == "acme-ai"
    assert entry.provider_id == "acme-ai"
    assert entry.envVars == ["ACME_AI_API_KEY"]

    api = JarvisPluginApi("acme-ai")
    if entry.register_fn:
        entry.register_fn(api)

    assert len(api.registered_providers) == 1
    prov = api.registered_providers[0]
    assert prov["id"] == "acme-ai"
    assert prov["label"] == "Acme AI"
