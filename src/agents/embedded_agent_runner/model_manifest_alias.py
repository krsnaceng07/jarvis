"""jarvis.agents.embedded_agent_runner.model_manifest_alias — plugin manifest alias resolution.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/model.manifest-alias.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`ManifestModelCatalogProviderTransport` — readonly alias
  transport shape (``api`` + ``baseUrl``).
- :data:`ManifestModelCatalogProviderAliasMetadata` — alias
  resolution result (``provider`` + optional ``ambiguous`` flag
  and optional ``transport``).
- :func:`resolve_manifest_model_catalog_provider_alias_metadata` —
  resolve the provider alias metadata from plugin manifests.
- :func:`canonicalize_manifest_model_catalog_provider_alias` —
  return the canonicalized provider id.
- :func:`resolve_manifest_model_catalog_provider_transport` —
  return the transport defaults owned by a retained alias.

Phase 7.3b — focused minimal port.

The OpenClaw source is tightly coupled to the plugin-metadata
snapshot, manifest registry, and plugin owner policy layers. The
Python port keeps the public surface but delegates the heavy
discovery to installable hooks so the host can plug in the real
plugin-manifest layer as it lands.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from .model_static_id import static_model_id_matches


#: Manifest model catalog provider transport shape. Mirrors
#: :class:`ManifestModelCatalogProviderTransport``
#: (``model.manifest-alias.ts:117-119``).
ManifestModelCatalogProviderTransport = Dict[str, Any]


#: Manifest model catalog provider alias metadata. Mirrors
#: :class:`ManifestModelCatalogProviderAliasMetadata``
#: (``model.manifest-alias.ts:121-125``).
ManifestModelCatalogProviderAliasMetadata = Dict[str, Any]


#: Provider id normalizer. The OpenClaw source uses
#: ``normalizeProviderId`` from
#: ``@openclaw/model-catalog-core/provider-id``. The Python port
#: delegates to an installable normalizer.
_PROVIDER_ID_NORMALIZER: Callable[[str], str] = lambda value: (value or "").strip().lower()


def set_provider_id_normalizer(
    normalizer: Callable[[str], str],
) -> None:
    """Install a custom provider id normalizer."""
    global _PROVIDER_ID_NORMALIZER
    _PROVIDER_ID_NORMALIZER = normalizer


def _normalize_provider_id(value: str) -> str:
    return _PROVIDER_ID_NORMALIZER(value or "")


#: Plugin-manifest registry loader. The host installs the real
#: ``loadPluginManifestRegistry`` when the plugin-manifest layer
#: lands. The default returns ``{"plugins": []}``.
_LOAD_PLUGIN_MANIFEST_REGISTRY: Callable[..., Dict[str, Any]] = (
    lambda **_kwargs: {"plugins": []}
)


def set_load_plugin_manifest_registry_hook(
    hook: Callable[..., Dict[str, Any]],
) -> None:
    """Install a custom plugin-manifest registry loader hook."""
    global _LOAD_PLUGIN_MANIFEST_REGISTRY
    _LOAD_PLUGIN_MANIFEST_REGISTRY = hook


#: Current plugin-metadata snapshot getter. The host installs the
#: real ``getCurrentPluginMetadataSnapshot`` when the snapshot
#: layer lands. The default returns ``None``.
_GET_CURRENT_PLUGIN_METADATA_SNAPSHOT: Callable[..., Optional[Dict[str, Any]]] = (
    lambda **_kwargs: None
)


def set_get_current_plugin_metadata_snapshot_hook(
    hook: Callable[..., Optional[Dict[str, Any]]],
) -> None:
    """Install a custom current-plugin-metadata-snapshot getter hook."""
    global _GET_CURRENT_PLUGIN_METADATA_SNAPSHOT
    _GET_CURRENT_PLUGIN_METADATA_SNAPSHOT = hook


#: Plugin eligibility check. The host installs the real
#: ``isActivatedManifestOwner`` / ``isBundledManifestOwner`` /
#: ``hasExplicitManifestOwnerTrust`` chain when the plugin-owner
#: policy layer lands. The default returns ``True`` so the
#: eligible filter is a no-op.
_IS_PLUGIN_ELIGIBLE: Callable[[Dict[str, Any], Optional[Dict[str, Any]]], bool] = (
    lambda _plugin, _normalized_config: True
)


def set_is_plugin_eligible_hook(
    hook: Callable[[Dict[str, Any], Optional[Dict[str, Any]]], bool],
) -> None:
    """Install a custom plugin eligibility check hook."""
    global _IS_PLUGIN_ELIGIBLE
    _IS_PLUGIN_ELIGIBLE = hook


def _list_eligible_manifest_plugins(
    *,
    cfg: Optional[Dict[str, Any]],
    plugins: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Filter the plugin list to eligible manifest owners.

    Mirrors :func:`listEligibleManifestModelCatalogAliasPlugins``
    (``model.manifest-alias.ts:144-165``).
    """
    out: List[Dict[str, Any]] = []
    for plugin in plugins:
        if not _IS_PLUGIN_ELIGIBLE(plugin, cfg):
            continue
        out.append(plugin)
    return out


def _has_model_catalog_alias_transport_override(alias: Dict[str, Any]) -> bool:
    """Return True if the alias declares an api or baseUrl override.

    Mirrors :func:`hasModelCatalogAliasTransportOverride``
    (``model.manifest-alias.ts:19-21``).
    """
    api = alias.get("api")
    base_url = alias.get("baseUrl")
    return bool(
        (isinstance(api, str) and api.strip())
        or (isinstance(base_url, str) and base_url.strip())
    )


def _has_model_catalog_alias_endpoint_surface(alias: Dict[str, Any]) -> bool:
    """Return True if the alias declares a baseUrl.

    Mirrors :func:`hasModelCatalogAliasEndpointSurface``
    (``model.manifest-alias.ts:23-25``).
    """
    base_url = alias.get("baseUrl")
    return bool(isinstance(base_url, str) and base_url.strip())


def _resolve_manifest_alias_target_api(
    *,
    plugin: Dict[str, Any],
    provider: str,
    model_id: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve the target API + baseUrl for a manifest alias.

    Mirrors :func:`resolveManifestAliasTargetApi``
    (``model.manifest-alias.ts:167-189``). Returns a tuple of
    ``(api, baseUrl)`` so the caller can build a transport dict.
    """
    catalog = plugin.get("modelCatalog") or {}
    providers = catalog.get("providers") or {}
    provider_entry: Optional[Dict[str, Any]] = None
    for entry_provider, entry in providers.items():
        if _normalize_provider_id(entry_provider) == provider:
            provider_entry = entry
            break
    if not provider_entry:
        return None, None
    target_model_id = (model_id or "").strip()
    model: Optional[Dict[str, Any]] = None
    if target_model_id:
        for candidate in provider_entry.get("models") or []:
            if static_model_id_matches(
                candidate_id=candidate.get("id", ""),
                provider=provider,
                model_id=target_model_id,
            ):
                model = candidate
                break
    api_value = model.get("api") if model else None
    base_url_value = model.get("baseUrl") if model else None
    if isinstance(api_value, str) and api_value.strip():
        api = api_value.strip()
    else:
        provider_api = provider_entry.get("api")
        api = provider_api.strip() if isinstance(provider_api, str) and provider_api.strip() else None
    if isinstance(base_url_value, str) and base_url_value.strip():
        base_url = base_url_value.strip()
    else:
        provider_base_url = provider_entry.get("baseUrl")
        base_url = (
            provider_base_url.strip()
            if isinstance(provider_base_url, str) and provider_base_url.strip()
            else None
        )
    return api, base_url


def _resolve_manifest_provider_alias(
    *,
    provider: str,
    model_id: Optional[str],
    cfg: Optional[Dict[str, Any]],
    plugins: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Resolve the manifest provider alias.

    Mirrors :func:`resolveManifestModelCatalogProviderAlias``
    (``model.manifest-alias.ts:191-288``). The Python port keeps
    the same surface (returns one of ``"none"`` / ``"conflict"`` /
    ``"incomplete-transport"`` / ``"canonical"`` / ``"transport"``)
    but the heavy plugin-claim collection is delegated to
    :data:`_IS_PLUGIN_ELIGIBLE` and the real provider-alias
    resolution lives in the host.
    """
    eligible = _list_eligible_manifest_plugins(cfg=cfg, plugins=plugins)
    if not eligible:
        return {"kind": "none"}
    claims: List[Dict[str, Any]] = []
    for plugin in eligible:
        target_api, target_base_url = _resolve_manifest_alias_target_api(
            plugin=plugin, provider=provider, model_id=model_id
        )
        transport: Dict[str, Any] = {}
        if target_api:
            transport["api"] = target_api
        if target_base_url:
            transport["baseUrl"] = target_base_url
        retains_transport_alias = bool(transport)
        incomplete = not retains_transport_alias
        claims.append(
            {
                "incompleteTransport": incomplete,
                "targetProvider": provider,
                "retainsTransportAlias": retains_transport_alias,
                "transport": transport,
            }
        )
    if not claims:
        return {"kind": "none"}
    if len(claims) > 1:
        # Multiple plugin claims — conflict unless they all agree.
        target = claims[0].get("targetProvider")
        if all(c.get("targetProvider") == target for c in claims):
            return {"kind": "canonical", "provider": target}
        return {"kind": "conflict"}
    claim = claims[0]
    if claim.get("incompleteTransport"):
        return {"kind": "incomplete-transport"}
    if claim.get("retainsTransportAlias") and claim.get("transport"):
        return {"kind": "transport", "transport": claim["transport"]}
    return {"kind": "canonical", "provider": claim.get("targetProvider", provider)}


def resolve_manifest_model_catalog_provider_alias_metadata(
    *,
    provider: str,
    model_id: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    workspace_dir: Optional[str] = None,
    env: Optional[Dict[str, Any]] = None,
) -> ManifestModelCatalogProviderAliasMetadata:
    """Resolve the manifest provider alias metadata.

    Mirrors :func:`resolveManifestModelCatalogProviderAliasMetadata``
    (``model.manifest-alias.ts:290-341``).
    """
    normalized = _normalize_provider_id(provider or "")
    if not normalized:
        return {"provider": provider}
    # The Python port uses the env as a "process-env" stand-in;
    # the current snapshot is the default path (matching the
    # OpenClaw source's `env === process.env` short-circuit).
    snapshot = _GET_CURRENT_PLUGIN_METADATA_SNAPSHOT(
        config=cfg,
        workspace_dir=workspace_dir,
        env=env,
        **(dict(require_default_discovery_context=True) if cfg is None else {}),
    )
    plugins: List[Dict[str, Any]]
    if snapshot is not None:
        plugins = list(snapshot.get("plugins") or [])
    else:
        registry = _LOAD_PLUGIN_MANIFEST_REGISTRY(
            config=cfg,
            workspace_dir=workspace_dir,
            env=env,
        )
        plugins = list(registry.get("plugins") or [])
    resolved = _resolve_manifest_provider_alias(
        provider=normalized,
        model_id=model_id,
        cfg=cfg,
        plugins=plugins,
    )
    kind = resolved.get("kind")
    if kind == "canonical":
        return {"provider": resolved.get("provider", provider)}
    if kind == "transport":
        return {
            "provider": provider,
            "transport": resolved.get("transport", {}),
        }
    if kind in ("conflict", "incomplete-transport"):
        return {"provider": provider, "ambiguous": True}
    return {"provider": provider}


def canonicalize_manifest_model_catalog_provider_alias(
    *,
    provider: str,
    model_id: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    workspace_dir: Optional[str] = None,
    env: Optional[Dict[str, Any]] = None,
) -> str:
    """Return the canonicalized provider id from manifest alias metadata.

    Mirrors :func:`canonicalizeManifestModelCatalogProviderAlias``
    (``model.manifest-alias.ts:344-352``).
    """
    return resolve_manifest_model_catalog_provider_alias_metadata(
        provider=provider,
        model_id=model_id,
        cfg=cfg,
        workspace_dir=workspace_dir,
        env=env,
    )["provider"]


def resolve_manifest_model_catalog_provider_transport(
    *,
    provider: str,
    model_id: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    workspace_dir: Optional[str] = None,
    env: Optional[Dict[str, Any]] = None,
) -> Optional[ManifestModelCatalogProviderTransport]:
    """Return the transport defaults owned by a retained manifest alias.

    Mirrors :func:`resolveManifestModelCatalogProviderTransport``
    (``model.manifest-alias.ts:355-363``).
    """
    return resolve_manifest_model_catalog_provider_alias_metadata(
        provider=provider,
        model_id=model_id,
        cfg=cfg,
        workspace_dir=workspace_dir,
        env=env,
    ).get("transport")


__all__ = [
    "ManifestModelCatalogProviderAliasMetadata",
    "ManifestModelCatalogProviderTransport",
    "canonicalize_manifest_model_catalog_provider_alias",
    "resolve_manifest_model_catalog_provider_alias_metadata",
    "resolve_manifest_model_catalog_provider_transport",
    "set_get_current_plugin_metadata_snapshot_hook",
    "set_is_plugin_eligible_hook",
    "set_load_plugin_manifest_registry_hook",
    "set_provider_id_normalizer",
]
