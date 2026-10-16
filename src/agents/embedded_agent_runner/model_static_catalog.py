"""jarvis.agents.embedded_agent_runner.model_static_catalog — bundled plugin static catalog resolvers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/model.static-catalog.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`bundled_static_catalog_provider_uses_runtime_augment` —
  return True if a bundled static catalog asks runtime discovery
  to augment its rows.
- :func:`create_bundled_static_catalog_model_resolver` —
  build a process-stable resolver that maps (provider, modelId)
  to a runtime model record.
- :func:`resolve_bundled_static_catalog_model` — single-lookup
  helper around the resolver.
- :func:`load_bundled_provider_static_catalog_context_models` —
  return a list of context-models for a bundled provider.
- :func:`create_bundled_provider_static_catalog_model_resolver` —
  provider-scoped model resolver.
- :func:`create_bundled_provider_static_catalog_context_resolver` —
  provider-scoped context resolver.
- :func:`resolve_bundled_provider_static_catalog_model` — single
  lookup against the provider-scoped resolver.
- Re-exports :func:`canonicalize_manifest_model_catalog_provider_alias`,
  :func:`resolve_manifest_model_catalog_provider_alias_metadata`,
  :func:`resolve_manifest_model_catalog_provider_transport`,
  and the matching ``ManifestModelCatalogProviderAliasMetadata``
  / ``ManifestModelCatalogProviderTransport`` TypedDicts.

Phase 7.3d — focused minimal port.

The OpenClaw source is tightly coupled to the bundled plugin
manifest, model catalog, and provider-resolver layers. The
Python port keeps the public surface but delegates the heavy
plugin iteration to installable hooks so the host can plug in
the real bundled-manifest layer as it lands.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .model_manifest_alias import (
    canonicalize_manifest_model_catalog_provider_alias as _canonicalize_alias,
)
from .model_manifest_alias import (
    resolve_manifest_model_catalog_provider_alias_metadata as _resolve_alias_metadata,
)
from .model_manifest_alias import (
    resolve_manifest_model_catalog_provider_transport as _resolve_alias_transport,
)
from .model_static_id import static_model_id_matches


# Re-exports (mirrors the OpenClaw source's `export { ... } from
# "./model.manifest-alias.js"` block).
def canonicalize_manifest_model_catalog_provider_alias(**kwargs: Any) -> str:
    """Re-export of :func:`model_manifest_alias.canonicalize_manifest_model_catalog_provider_alias`."""
    return _canonicalize_alias(**kwargs)


def resolve_manifest_model_catalog_provider_alias_metadata(
    **kwargs: Any,
) -> Dict[str, Any]:
    """Re-export of :func:`model_manifest_alias.resolve_manifest_model_catalog_provider_alias_metadata`."""
    return _resolve_alias_metadata(**kwargs)


def resolve_manifest_model_catalog_provider_transport(
    **kwargs: Any,
) -> Optional[Dict[str, Any]]:
    """Re-export of :func:`model_manifest_alias.resolve_manifest_model_catalog_provider_transport`."""
    return _resolve_alias_transport(**kwargs)


#: Default context tokens (mirrors ``DEFAULT_CONTEXT_TOKENS``).
DEFAULT_CONTEXT_TOKENS: int = 200_000


def _default_provider_id_normalizer(value: str) -> str:
    return (value or "").strip().lower()


#: Provider id normalizer hook.
_PROVIDER_ID_NORMALIZER: Callable[[str], str] = _default_provider_id_normalizer


def set_provider_id_normalizer(
    normalizer: Callable[[str], str],
) -> None:
    """Install a custom provider id normalizer hook."""
    global _PROVIDER_ID_NORMALIZER
    _PROVIDER_ID_NORMALIZER = normalizer


def _normalize_provider_id(value: str) -> str:
    return _PROVIDER_ID_NORMALIZER(value or "")


#: Bundled static catalog plugins lister. The host installs the
#: real ``listBundledStaticCatalogPlugins`` when the bundled
#: manifest layer lands. The default returns an empty list.
def _default_bundled_static_catalog_plugins(**_kwargs: Any) -> List[Dict[str, Any]]:
    return []


_LIST_BUNDLED_STATIC_CATALOG_PLUGINS: Callable[..., List[Dict[str, Any]]] = (
    _default_bundled_static_catalog_plugins
)


def set_list_bundled_static_catalog_plugins_hook(
    hook: Callable[..., List[Dict[str, Any]]],
) -> None:
    """Install a custom bundled-static-catalog plugins lister hook."""
    global _LIST_BUNDLED_STATIC_CATALOG_PLUGINS
    _LIST_BUNDLED_STATIC_CATALOG_PLUGINS = hook


#: Manifest model catalog rows planner. The host installs the
#: real ``planManifestModelCatalogRows`` when the
#: model-catalog-planner layer lands. The default returns
#: ``{"rows": []}``.
def _default_manifest_model_catalog_rows(**_kwargs: Any) -> Dict[str, Any]:
    return {"rows": []}


_PLAN_MANIFEST_MODEL_CATALOG_ROWS: Callable[..., Dict[str, Any]] = (
    _default_manifest_model_catalog_rows
)


def set_plan_manifest_model_catalog_rows_hook(
    hook: Callable[..., Dict[str, Any]],
) -> None:
    """Install a custom manifest-model-catalog rows planner hook."""
    global _PLAN_MANIFEST_MODEL_CATALOG_ROWS
    _PLAN_MANIFEST_MODEL_CATALOG_ROWS = hook


#: Plugin row builder. The host installs the real
#: ``buildBundledManifestModelCatalogPluginRow`` when the
#: model-catalog-planner layer lands. The default returns the
#: input row unchanged.
def _default_plugin_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return row


_BUILD_PLUGIN_ROW: Callable[[Dict[str, Any]], Dict[str, Any]] = _default_plugin_row


def set_build_plugin_row_hook(
    hook: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> None:
    """Install a custom bundled-manifest plugin row builder hook."""
    global _BUILD_PLUGIN_ROW
    _BUILD_PLUGIN_ROW = hook


def _normalize_static_catalog_input(input_value: Any) -> List[str]:
    """Normalize a static catalog ``input`` field.

    Mirrors :func:`normalizeStaticCatalogInput``
    (``model.static-catalog.ts:55-62``).
    """
    if not isinstance(input_value, list):
        return ["text"]
    normalized = [item for item in input_value if item == "text" or item == "image"]
    return normalized if normalized else ["text"]


def _normalize_static_catalog_cost(cost: Any) -> Dict[str, Any]:
    """Normalize a static catalog ``cost`` field.

    Mirrors :func:`normalizeStaticCatalogCost``
    (``model.static-catalog.ts:64-73``).
    """
    if not isinstance(cost, dict):
        cost = {}
    return {
        "input": cost.get("input") if cost.get("input") is not None else 0,
        "output": cost.get("output") if cost.get("output") is not None else 0,
        "cacheRead": cost.get("cacheRead") if cost.get("cacheRead") is not None else 0,
        "cacheWrite": cost.get("cacheWrite") if cost.get("cacheWrite") is not None else 0,
    }


def _model_from_static_catalog_row(
    row: Dict[str, Any],
) -> Dict[str, Any]:
    """Convert a normalized catalog row into a runtime model record.

    Mirrors :func:`modelFromStaticCatalogRow``
    (``model.static-catalog.ts:76-94``).
    """
    return {
        "id": row.get("id", ""),
        "name": row.get("name") or row.get("id", ""),
        "provider": row.get("provider", ""),
        "api": row.get("api") or "openai-responses",
        "baseUrl": row.get("baseUrl") or "",
        "reasoning": row.get("reasoning"),
        "input": _normalize_static_catalog_input(row.get("input")),
        "cost": _normalize_static_catalog_cost(row.get("cost")),
        "contextWindow": (
            row.get("contextWindow")
            if row.get("contextWindow") is not None
            else DEFAULT_CONTEXT_TOKENS
        ),
        "contextTokens": row.get("contextTokens"),
        "maxTokens": (
            row.get("maxTokens") if row.get("maxTokens") is not None else DEFAULT_CONTEXT_TOKENS
        ),
        "contextWindows": row.get("contextWindows"),
        "contextWindowDefault": row.get("contextWindowDefault"),
        "thinkingLevelMap": (
            dict(row["thinkingLevelMap"]) if isinstance(row.get("thinkingLevelMap"), dict) else None
        ),
        "headers": row.get("headers"),
        "compat": row.get("compat"),
        "mediaInput": row.get("mediaInput"),
    }


def _row_matches_model(
    *,
    row: Dict[str, Any],
    provider: str,
    model_id: str,
) -> bool:
    """Return True if the catalog row matches the target provider/model.

    Mirrors :func:`rowMatchesModel``
    (``model.static-catalog.ts:42-53``).
    """
    return static_model_id_matches(
        candidate_id=row.get("id", ""),
        provider=provider,
        model_id=model_id,
        row_provider=row.get("provider"),
    )


def bundled_static_catalog_provider_uses_runtime_augment(
    *,
    provider: str,
    cfg: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, Any]] = None,
) -> bool:
    """Return True if a bundled static catalog asks for runtime augment.

    Mirrors :func:`bundledStaticCatalogProviderUsesRuntimeAugment``
    (``model.static-catalog.ts:168-194``).
    """
    normalized = _normalize_provider_id(provider or "")
    if not normalized:
        return False
    plugins = _LIST_BUNDLED_STATIC_CATALOG_PLUGINS(cfg=cfg, env=env)
    for plugin in plugins:
        catalog = plugin.get("modelCatalog")
        if not catalog or catalog.get("runtimeAugment") is not True:
            continue
        if any(
            _normalize_provider_id(candidate) == normalized
            for candidate in (catalog.get("providers") or {}).keys()
        ):
            return True
        if any(
            _normalize_provider_id(candidate) == normalized
            for candidate in (catalog.get("aliases") or {}).keys()
        ):
            return True
    return False


def create_bundled_static_catalog_model_resolver(
    params: Optional[Dict[str, Any]] = None,
) -> Callable[[Dict[str, str]], Optional[Dict[str, Any]]]:
    """Build a process-stable bundled static catalog model resolver.

    Mirrors :func:`createBundledStaticCatalogModelResolver``
    (``model.static-catalog.ts:221-265``).
    """
    params = params or {}
    bundled_plugins = _LIST_BUNDLED_STATIC_CATALOG_PLUGINS(
        cfg=params.get("cfg"),
        env=params.get("env"),
    )
    plans: Dict[str, Dict[str, Any]] = {}
    return lambda lookup: _resolve_with_plans(
        lookup=lookup,
        bundled_plugins=bundled_plugins,
        plans=plans,
    )


def _resolve_with_plans(
    *,
    lookup: Dict[str, str],
    bundled_plugins: List[Dict[str, Any]],
    plans: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Resolve a lookup against precomputed plans.

    Helper for :func:`create_bundled_static_catalog_model_resolver`.
    """
    provider = _normalize_provider_id(lookup.get("provider", ""))
    if not provider or not (lookup.get("modelId") or "").strip():
        return None
    if not bundled_plugins:
        return None
    plan = plans.get(provider)
    if plan is None:
        plan = _PLAN_MANIFEST_MODEL_CATALOG_ROWS(
            registry={"plugins": bundled_plugins},
            cfg=None,
            provider=provider,
        )
        plans[provider] = plan
    rows = plan.get("rows") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not _row_matches_model(row=row, provider=provider, model_id=lookup["modelId"]):
            continue
        return _model_from_static_catalog_row(_BUILD_PLUGIN_ROW(row))
    return None


def resolve_bundled_static_catalog_model(
    *,
    provider: str,
    model_id: str,
    cfg: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Single-lookup variant of the bundled static catalog resolver.

    Mirrors :func:`resolveBundledStaticCatalogModel``
    (``model.static-catalog.ts:267-...``).
    """
    resolver = create_bundled_static_catalog_model_resolver({"cfg": cfg, "env": env})
    return resolver({"provider": provider, "modelId": model_id})


async def load_bundled_provider_static_catalog_context_models(
    *,
    provider: str,
    cfg: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Load the context models for a bundled provider.

    Mirrors :func:`loadBundledProviderStaticCatalogContextModels``
    (``model.static-catalog.ts:368-...``).
    """
    normalized = _normalize_provider_id(provider or "")
    if not normalized:
        return []
    plugins = _LIST_BUNDLED_STATIC_CATALOG_PLUGINS(cfg=cfg, env=env)
    for plugin in plugins:
        catalog = plugin.get("modelCatalog") or {}
        provider_entry = (catalog.get("providers") or {}).get(normalized)
        if not provider_entry:
            continue
        models = provider_entry.get("models") or []
        return [model for model in models if isinstance(model, dict)]
    return []


def create_bundled_provider_static_catalog_model_resolver(
    params: Optional[Dict[str, Any]] = None,
) -> Callable[[Dict[str, str]], Optional[Dict[str, Any]]]:
    """Build a provider-scoped model resolver.

    Mirrors :func:`createBundledProviderStaticCatalogModelResolver``
    (``model.static-catalog.ts:460-...``).
    """
    params = params or {}
    provider = _normalize_provider_id(params.get("provider", ""))
    if not provider:
        return lambda _lookup: None
    plugins = _LIST_BUNDLED_STATIC_CATALOG_PLUGINS(
        cfg=params.get("cfg"),
        env=params.get("env"),
    )
    catalog_rows: List[Dict[str, Any]] = []
    for plugin in plugins:
        catalog = plugin.get("modelCatalog") or {}
        provider_entry = (catalog.get("providers") or {}).get(provider)
        if not provider_entry:
            continue
        for model in provider_entry.get("models") or []:
            if isinstance(model, dict):
                catalog_rows.append(model)
    if not catalog_rows:
        return lambda _lookup: None
    return lambda lookup: _resolve_provider_scoped(
        lookup=lookup, provider=provider, catalog_rows=catalog_rows
    )


def _resolve_provider_scoped(
    *,
    lookup: Dict[str, str],
    provider: str,
    catalog_rows: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if _normalize_provider_id(lookup.get("provider", "")) != provider:
        return None
    model_id = (lookup.get("modelId") or "").strip()
    if not model_id:
        return None
    for row in catalog_rows:
        if _row_matches_model(row=row, provider=provider, model_id=model_id):
            return _model_from_static_catalog_row(_BUILD_PLUGIN_ROW(row))
    return None


def create_bundled_provider_static_catalog_context_resolver(
    params: Optional[Dict[str, Any]] = None,
) -> Callable[[Dict[str, str]], Optional[Dict[str, Any]]]:
    """Build a provider-scoped context resolver.

    Mirrors :func:`createBundledProviderStaticCatalogContextResolver``
    (``model.static-catalog.ts:507-...``).
    """
    params = params or {}
    provider = _normalize_provider_id(params.get("provider", ""))
    if not provider:
        return lambda _lookup: None
    plugins = _LIST_BUNDLED_STATIC_CATALOG_PLUGINS(
        cfg=params.get("cfg"),
        env=params.get("env"),
    )
    rows_by_id: Dict[str, Dict[str, Any]] = {}
    for plugin in plugins:
        catalog = plugin.get("modelCatalog") or {}
        provider_entry = (catalog.get("providers") or {}).get(provider)
        if not provider_entry:
            continue
        for model in provider_entry.get("models") or []:
            if not isinstance(model, dict):
                continue
            model_id = (model.get("id") or "").strip()
            if model_id:
                rows_by_id[model_id] = model
    if not rows_by_id:
        return lambda _lookup: None
    return lambda lookup: _resolve_provider_context(
        lookup=lookup, provider=provider, rows_by_id=rows_by_id
    )


def _resolve_provider_context(
    *,
    lookup: Dict[str, str],
    provider: str,
    rows_by_id: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if _normalize_provider_id(lookup.get("provider", "")) != provider:
        return None
    model_id = (lookup.get("modelId") or "").strip()
    if not model_id:
        return None
    row = rows_by_id.get(model_id)
    if not row:
        return None
    return {
        "contextWindow": row.get("contextWindow") or DEFAULT_CONTEXT_TOKENS,
        "contextTokens": row.get("contextTokens"),
    }


async def resolve_bundled_provider_static_catalog_model(
    *,
    provider: str,
    model_id: str,
    cfg: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Single-lookup variant of the provider-scoped resolver.

    Mirrors :func:`resolveBundledProviderStaticCatalogModel``
    (``model.static-catalog.ts:539-...``).
    """
    resolver = create_bundled_provider_static_catalog_model_resolver(
        {"provider": provider, "cfg": cfg, "env": env}
    )
    return resolver({"provider": provider, "modelId": model_id})


__all__ = [
    "DEFAULT_CONTEXT_TOKENS",
    "bundled_static_catalog_provider_uses_runtime_augment",
    "canonicalize_manifest_model_catalog_provider_alias",
    "create_bundled_provider_static_catalog_context_resolver",
    "create_bundled_provider_static_catalog_model_resolver",
    "create_bundled_static_catalog_model_resolver",
    "load_bundled_provider_static_catalog_context_models",
    "resolve_bundled_provider_static_catalog_model",
    "resolve_bundled_static_catalog_model",
    "resolve_manifest_model_catalog_provider_alias_metadata",
    "resolve_manifest_model_catalog_provider_transport",
    "set_build_plugin_row_hook",
    "set_list_bundled_static_catalog_plugins_hook",
    "set_plan_manifest_model_catalog_rows_hook",
    "set_provider_id_normalizer",
]
