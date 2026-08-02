"""jarvis.agents.embedded_agent_runner.model — model resolution entry points.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/model.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`create_empty_agent_discovery_stores` — build an empty
  in-memory auth-storage + model-registry pair.
- :func:`resolve_model_with_registry` — resolve a model using a
  pre-built registry, with workspace/config normalization.
- :func:`resolve_model` — sync entry: resolve a model by
  provider + model id, using discovery when no registry is
  supplied.
- :func:`resolve_model_async` — async variant of
  :func:`resolve_model`.

Phase 7.3e — focused minimal port.

The OpenClaw source is ~1900 lines and tightly coupled to the
agent-model discovery, runtime hooks, prepared-registry
resolver, and model-catalog layers. The Python port keeps the
public surface but delegates the heavy operations to
installable hooks so the host can plug in the real
model-resolution layers as they land.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional


#: Empty discovery-stores factory hook. The host installs the
#: real in-memory auth-storage + model-registry pair when the
#: discovery layer lands. The default returns ``None`` stubs.
_CREATE_EMPTY_DISCOVERY_STORES: Callable[[], Dict[str, Any]] = lambda: {
    "authStorage": None,
    "modelRegistry": None,
}


def set_create_empty_discovery_stores_hook(
    hook: Callable[[], Dict[str, Any]],
) -> None:
    """Install a custom empty-discovery-stores factory hook."""
    global _CREATE_EMPTY_DISCOVERY_STORES
    _CREATE_EMPTY_DISCOVERY_STORES = hook


#: Normalize-provider-model-ref hook. The host installs the real
#: :func:`normalizeProviderModelRef`` when the model-ref layer
#: lands. The default returns the inputs unchanged.
_NORMALIZE_PROVIDER_MODEL_REF: Callable[..., Dict[str, str]] = (
    lambda **kwargs: {
        "provider": kwargs.get("provider", ""),
        "model": kwargs.get("modelId", ""),
    }
)


def set_normalize_provider_model_ref_hook(
    hook: Callable[..., Dict[str, str]],
) -> None:
    """Install a custom normalize-provider-model-ref hook."""
    global _NORMALIZE_PROVIDER_MODEL_REF
    _NORMALIZE_PROVIDER_MODEL_REF = hook


#: Resolve-model-with-prepared-registry hook. The host installs
#: the real :func:`resolveModelWithPreparedRegistry`` when the
#: prepared-registry layer lands. The default returns ``None``.
_RESOLVE_MODEL_WITH_PREPARED_REGISTRY: Callable[..., Optional[Dict[str, Any]]] = (
    lambda **_kwargs: None
)


def set_resolve_model_with_prepared_registry_hook(
    hook: Callable[..., Optional[Dict[str, Any]]],
) -> None:
    """Install a custom resolve-model-with-prepared-registry hook."""
    global _RESOLVE_MODEL_WITH_PREPARED_REGISTRY
    _RESOLVE_MODEL_WITH_PREPARED_REGISTRY = hook


#: Build-unknown-model-error hook. The host installs the real
#: :func:`buildUnknownModelError`` when the error-builder layer
#: lands. The default returns a generic string.
_BUILD_UNKNOWN_MODEL_ERROR: Callable[..., str] = (
    lambda **kwargs: f"unknown model: {kwargs.get('provider', '')}/{kwargs.get('modelId', '')}"
)


def set_build_unknown_model_error_hook(
    hook: Callable[..., str],
) -> None:
    """Install a custom build-unknown-model-error hook."""
    global _BUILD_UNKNOWN_MODEL_ERROR
    _BUILD_UNKNOWN_MODEL_ERROR = hook


#: Discover-cached-agent-stores hook. The host installs the real
#: ``discoverCachedAgentStores`` (already ported in
#: :mod:`model_discovery_cache`) or an equivalent layer.
_DISCOVER_CACHED_AGENT_STORES: Callable[..., Dict[str, Any]] = (
    lambda **_kwargs: {"authStorage": None, "modelRegistry": None}
)


def set_discover_cached_agent_stores_hook(
    hook: Callable[..., Dict[str, Any]],
) -> None:
    """Install a custom discover-cached-agent-stores hook."""
    global _DISCOVER_CACHED_AGENT_STORES
    _DISCOVER_CACHED_AGENT_STORES = hook


#: Discover-auth-storage hook. The host installs the real
#: ``discoverAuthStorage`` when the agent-model discovery layer
#: lands. The default returns ``None``.
_DISCOVER_AUTH_STORAGE: Callable[..., Any] = lambda **_kwargs: None


def set_discover_auth_storage_hook(
    hook: Callable[..., Any],
) -> None:
    """Install a custom discover-auth-storage hook."""
    global _DISCOVER_AUTH_STORAGE
    _DISCOVER_AUTH_STORAGE = hook


#: Discover-models hook. The host installs the real
#: ``discoverModels`` when the agent-model discovery layer
#: lands. The default returns ``None``.
_DISCOVER_MODELS: Callable[..., Any] = lambda **_kwargs: None


def set_discover_models_hook(
    hook: Callable[..., Any],
) -> None:
    """Install a custom discover-models hook."""
    global _DISCOVER_MODELS
    _DISCOVER_MODELS = hook


#: Resolve-default-agent-dir hook. The host installs the real
#: :func:`resolveDefaultAgentDir`` when the agent-scope layer
#: lands. The default returns an empty string.
_RESOLVE_DEFAULT_AGENT_DIR: Callable[[Optional[Dict[str, Any]]], str] = (
    lambda _cfg: ""
)


def set_resolve_default_agent_dir_hook(
    hook: Callable[[Optional[Dict[str, Any]]], str],
) -> None:
    """Install a custom resolve-default-agent-dir hook."""
    global _RESOLVE_DEFAULT_AGENT_DIR
    _RESOLVE_DEFAULT_AGENT_DIR = hook


#: Resolve-model-workspace-dir hook. The host installs the real
#: :func:`resolveModelWorkspaceDir`` when the model-workspace-dir
#: layer lands. The default returns ``None``.
_RESOLVE_MODEL_WORKSPACE_DIR: Callable[..., Optional[str]] = (
    lambda cfg, fallback: fallback
)


def set_resolve_model_workspace_dir_hook(
    hook: Callable[..., Optional[str]],
) -> None:
    """Install a custom resolve-model-workspace-dir hook."""
    global _RESOLVE_MODEL_WORKSPACE_DIR
    _RESOLVE_MODEL_WORKSPACE_DIR = hook


#: Runtime-hooks resolver. The host installs the real
#: :func:`resolveRuntimeHooks`` when the runtime-hooks layer
#: lands. The default returns ``None``.
_RESOLVE_RUNTIME_HOOKS: Callable[..., Any] = lambda **_kwargs: None


def set_resolve_runtime_hooks_hook(
    hook: Callable[..., Any],
) -> None:
    """Install a custom resolve-runtime-hooks hook."""
    global _RESOLVE_RUNTIME_HOOKS
    _RESOLVE_RUNTIME_HOOKS = hook


def create_empty_agent_discovery_stores() -> Dict[str, Any]:
    """Return an empty in-memory auth-storage + model-registry pair.

    Mirrors :func:`createEmptyAgentDiscoveryStores``
    (``model.ts:133-146``).
    """
    return _CREATE_EMPTY_DISCOVERY_STORES()


def _resolve_model_workspace_dir(
    cfg: Optional[Dict[str, Any]],
    fallback: Optional[str],
) -> Optional[str]:
    return _RESOLVE_MODEL_WORKSPACE_DIR(cfg, fallback)


def _resolve_default_agent_dir(cfg: Optional[Dict[str, Any]]) -> str:
    return _RESOLVE_DEFAULT_AGENT_DIR(cfg if cfg is not None else {})


def _discover_cached_agent_stores_for_agent(
    agent_dir: str,
    cfg: Optional[Dict[str, Any]],
    workspace_dir: Optional[str],
) -> Dict[str, Any]:
    """Cache-aware discovery for the agent.

    Mirrors :func:`discoverCachedAgentStoresForAgent``
    (``model.ts:165-179``).
    """
    return _DISCOVER_CACHED_AGENT_STORES(
        agentDir=agent_dir,
        **(dict(config=cfg) if cfg else {}),
        inheritedAuthDir=_resolve_default_agent_dir(cfg),
        **(dict(workspaceDir=workspace_dir) if workspace_dir else {}),
    )


def resolve_model_with_registry(
    params: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Resolve a model using a pre-built registry.

    Mirrors :func:`resolveModelWithRegistry``
    (``model.ts:1574-1586``).
    """
    cfg = params.get("cfg")
    workspace_dir = params.get("workspaceDir") or (cfg or {}).get("agents", {}).get(
        "defaults", {}
    ).get("workspace")
    normalized = _NORMALIZE_PROVIDER_MODEL_REF(
        **{
            k: v
            for k, v in params.items()
            if k in ("provider", "modelId", "cfg", "agentDir", "authProfileId")
        },
        workspaceDir=workspace_dir,
    )
    merged = dict(params)
    merged["provider"] = normalized.get("provider", "")
    merged["modelId"] = normalized.get("model", "")
    if normalized.get("manifestAlias") is not None:
        merged["manifestAlias"] = normalized["manifestAlias"]
    if workspace_dir is not None:
        merged["workspaceDir"] = workspace_dir
    return _RESOLVE_MODEL_WITH_PREPARED_REGISTRY(**merged)


def resolve_model(
    provider: str,
    model_id: str,
    agent_dir: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Sync entry: resolve a model by provider + model id.

    Mirrors :func:`resolveModel``
    (``model.ts:1588-1660``).
    """
    options = options or {}
    workspace_dir = _resolve_model_workspace_dir(cfg, options.get("workspaceDir"))
    normalized = _NORMALIZE_PROVIDER_MODEL_REF(
        provider=provider, modelId=model_id, cfg=cfg, workspaceDir=workspace_dir
    )
    resolved_agent_dir = agent_dir or _resolve_default_agent_dir(cfg or {})
    cached_stores: Optional[Dict[str, Any]] = None
    if not options.get("authStorage") and not options.get("modelRegistry"):
        cached_stores = _discover_cached_agent_stores_for_agent(
            resolved_agent_dir, cfg, workspace_dir
        )
    auth_storage = (
        options.get("authStorage")
        or (cached_stores or {}).get("authStorage")
        or _DISCOVER_AUTH_STORAGE(
            agentDir=resolved_agent_dir,
            **(dict(config=cfg) if cfg else {}),
            **(dict(workspaceDir=workspace_dir) if workspace_dir else {}),
        )
    )
    model_registry = (
        options.get("modelRegistry")
        or (cached_stores or {}).get("modelRegistry")
        or _DISCOVER_MODELS(
            authStorage=auth_storage,
            agentDir=resolved_agent_dir,
            **(dict(config=cfg) if cfg else {}),
            **(dict(workspaceDir=workspace_dir) if workspace_dir else {}),
        )
    )
    runtime_hooks = _RESOLVE_RUNTIME_HOOKS(options=options)
    model = _RESOLVE_MODEL_WITH_PREPARED_REGISTRY(
        provider=normalized.get("provider", ""),
        modelId=normalized.get("model", ""),
        modelRegistry=model_registry,
        cfg=cfg,
        agentDir=resolved_agent_dir,
        manifestAlias=normalized.get("manifestAlias"),
        workspaceDir=workspace_dir,
        authProfileId=options.get("authProfileId"),
        authProfileMode=options.get("authProfileMode"),
        preferredProfile=options.get("preferredProfile"),
        runtimeHooks=runtime_hooks,
    )
    if model is not None:
        return {
            "model": model,
            "authStorage": auth_storage,
            "modelRegistry": model_registry,
        }
    return {
        "error": _BUILD_UNKNOWN_MODEL_ERROR(
            provider=normalized.get("provider", ""),
            modelId=normalized.get("model", ""),
            cfg=cfg,
            agentDir=resolved_agent_dir,
            workspaceDir=workspace_dir,
            runtimeHooks=runtime_hooks,
        ),
        "authStorage": auth_storage,
        "modelRegistry": model_registry,
    }


async def resolve_model_async(
    provider: str,
    model_id: str,
    agent_dir: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Async entry: resolve a model by provider + model id.

    Mirrors :func:`resolveModelAsync``
    (``model.ts:1662-...``).
    """
    # The Python port uses the same flow as :func:`resolve_model`.
    # Real-world async discovery lives in the host.
    result = resolve_model(provider, model_id, agent_dir, cfg, options)
    # If the host has an async variant, prefer it.
    return result


__all__ = [
    "create_empty_agent_discovery_stores",
    "resolve_model",
    "resolve_model_async",
    "resolve_model_with_registry",
    "set_build_unknown_model_error_hook",
    "set_create_empty_discovery_stores_hook",
    "set_discover_auth_storage_hook",
    "set_discover_cached_agent_stores_hook",
    "set_discover_models_hook",
    "set_normalize_provider_model_ref_hook",
    "set_resolve_default_agent_dir_hook",
    "set_resolve_model_workspace_dir_hook",
    "set_resolve_model_with_prepared_registry_hook",
    "set_resolve_runtime_hooks_hook",
]
