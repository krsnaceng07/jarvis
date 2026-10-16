"""jarvis_sdk.provider_entry — Provider plugin entry contracts & single-provider builder.

OpenClaw parity: mirrors
``openclaw-main/src/plugin-sdk/provider-entry.ts`` and
``openclaw-main/src/plugin-sdk/provider-auth.ts``.

Features:
- `ProviderCatalogOrder`: `"simple"` | `"profile"` | `"paired"` | `"late"`
- `ProviderApiKeyAuthOptions`: Dataclass defining API key auth method options (`providerId`, `methodId`, `label`, `envVar`, `flagName`, `defaultModel`).
- `create_provider_api_key_auth_method()`: Helper for creating API key auth configuration.
- `SingleProviderPluginDefinition`: Dataclass defining a single-provider plugin definition.
- `define_single_provider_plugin_entry()`: Factory function creating a single-provider plugin entry definition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from .plugin_entry import JarvisPluginApi, PluginEntryDefinition

ProviderCatalogOrder = Literal["simple", "profile", "paired", "late"]


@dataclass
class ProviderApiKeyAuthOptions:
    providerId: str
    methodId: str = "api-key"
    label: str = "API key"
    hint: str | None = None
    optionKey: str | None = None
    flagName: str | None = None
    envVar: str | None = None
    promptMessage: str | None = None
    defaultModel: str | None = None


def create_provider_api_key_auth_method(
    provider_id: str,
    method_id: str = "api-key",
    label: str = "API key",
    env_var: str | None = None,
    flag_name: str | None = None,
    default_model: str | None = None,
) -> ProviderApiKeyAuthOptions:
    """Create an API key authentication method definition for a provider."""
    return ProviderApiKeyAuthOptions(
        providerId=provider_id,
        methodId=method_id,
        label=label,
        envVar=env_var,
        flagName=flag_name,
        defaultModel=default_model,
    )


@dataclass
class SingleProviderPluginDefinition(PluginEntryDefinition):
    provider_id: str = ""
    provider_label: str = ""
    docsPath: str | None = None
    envVars: list[str] = field(default_factory=list)
    auth: list[ProviderApiKeyAuthOptions] = field(default_factory=list)
    catalog_order: ProviderCatalogOrder = "simple"
    build_provider: Callable[..., Any] | None = None
    build_static_provider: Callable[..., Any] | None = None
    resolve_dynamic_model: Callable[..., Any] | None = None

    @property
    def register_fn(self) -> Callable[[Any], None]:
        return self.register


def define_single_provider_plugin_entry(
    id: str,
    name: str,
    description: str,
    provider_label: str,
    docs_path: str | None = None,
    env_vars: list[str] | None = None,
    auth: list[ProviderApiKeyAuthOptions] | None = None,
    catalog_order: ProviderCatalogOrder = "simple",
    build_provider: Callable[..., Any] | None = None,
    build_static_provider: Callable[..., Any] | None = None,
    resolve_dynamic_model: Callable[..., Any] | None = None,
) -> SingleProviderPluginDefinition:
    """Define a single-provider plugin entry point."""
    prov_id = id
    clean_env = env_vars or []
    clean_auth = auth or []

    def register_fn(api: JarvisPluginApi) -> None:
        prov_cfg = {
            "id": prov_id,
            "label": provider_label,
            "docsPath": docs_path,
            "envVars": clean_env,
            "auth": clean_auth,
            "catalogOrder": catalog_order,
            "buildProvider": build_provider,
            "buildStaticProvider": build_static_provider,
            "resolveDynamicModel": resolve_dynamic_model,
        }
        api.register_provider(prov_cfg)

    return SingleProviderPluginDefinition(
        id=id,
        name=name,
        description=description,
        kind="standard",
        register=register_fn,
        provider_id=prov_id,
        provider_label=provider_label,
        docsPath=docs_path,
        envVars=clean_env,
        auth=clean_auth,
        catalog_order=catalog_order,
        build_provider=build_provider,
        build_static_provider=build_static_provider,
        resolve_dynamic_model=resolve_dynamic_model,
    )


__all__ = [
    "ProviderApiKeyAuthOptions",
    "ProviderCatalogOrder",
    "SingleProviderPluginDefinition",
    "create_provider_api_key_auth_method",
    "define_single_provider_plugin_entry",
]
