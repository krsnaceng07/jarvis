"""jarvis.agents.embedded_agent_runner.extra_params — model extra params + transport overrides.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/extra-params.ts``.

Public surface:

- :func:`resolve_extra_params`
- :func:`resolve_prepared_extra_params`
- :func:`resolve_agent_transport_override`
- :func:`resolve_explicit_settings_transport`
- :func:`apply_extra_params_to_agent`
- :func:`clear_prepared_extra_params_cache`
- :func:`reset_provider_runtime_deps_for_test`
- :func:`set_provider_runtime_deps_for_test`
- :data:`REQUEST_SCOPED_EXTRA_PARAM_KEYS`

Phase 7.6h-6 — focused minimal port.
"""
from __future__ import annotations

import copy
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set


_log = logging.getLogger("jarvis.agents.embedded_agent_runner.extra_params")


#: Keys that are scoped to a single request and must not be cached.
REQUEST_SCOPED_EXTRA_PARAM_KEYS: Set[str] = {"response_format", "responseFormat", "stop"}


# Installable hooks ---------------------------------------------------------

_resolve_extra_params_hook = None
_resolve_prepared_extra_params_hook = None
_resolve_agent_transport_override_hook = None
_resolve_explicit_settings_transport_hook = None
_apply_extra_params_to_agent_hook = None
_prepare_provider_extra_params_dep = None
_resolve_provider_extra_params_for_transport_dep = None
_wrap_provider_stream_fn_dep = None


def set_resolve_extra_params_hook(fn) -> None:
    global _resolve_extra_params_hook
    _resolve_extra_params_hook = fn


def set_resolve_prepared_extra_params_hook(fn) -> None:
    global _resolve_prepared_extra_params_hook
    _resolve_prepared_extra_params_hook = fn


def set_resolve_agent_transport_override_hook(fn) -> None:
    global _resolve_agent_transport_override_hook
    _resolve_agent_transport_override_hook = fn


def set_resolve_explicit_settings_transport_hook(fn) -> None:
    global _resolve_explicit_settings_transport_hook
    _resolve_explicit_settings_transport_hook = fn


def set_apply_extra_params_to_agent_hook(fn) -> None:
    global _apply_extra_params_to_agent_hook
    _apply_extra_params_to_agent_hook = fn


def set_prepare_provider_extra_params_dep(fn) -> None:
    global _prepare_provider_extra_params_dep
    _prepare_provider_extra_params_dep = fn


def set_resolve_provider_extra_params_for_transport_dep(fn) -> None:
    global _resolve_provider_extra_params_for_transport_dep
    _resolve_provider_extra_params_for_transport_dep = fn


def set_wrap_provider_stream_fn_dep(fn) -> None:
    global _wrap_provider_stream_fn_dep
    _wrap_provider_stream_fn_dep = fn


#: Process-local prepared-extra-params cache keyed by OpenClawConfig.
_prepared_extra_params_cache: Dict[int, Dict[str, Dict[str, Any]]] = {}


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _sanitize_extra_params_record(
    value: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not value:
        return None
    return {
        k: v
        for k, v in value.items()
        if k not in ("__proto__", "prototype", "constructor")
    }


def _strip_request_scoped_extra_params(
    value: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not value:
        return None
    filtered = {k: v for k, v in value.items() if k not in REQUEST_SCOPED_EXTRA_PARAM_KEYS}
    return filtered or None


def _has_request_scoped_extra_params(value: Optional[Dict[str, Any]]) -> bool:
    if not value:
        return False
    return any(k in value for k in REQUEST_SCOPED_EXTRA_PARAM_KEYS)


def _has_function_extra_param_value(value: Optional[Dict[str, Any]]) -> bool:
    if not value:
        return False
    return any(callable(v) for v in value.values())


def _resolve_supported_transport(value: Any) -> Optional[str]:
    if value in ("sse", "websocket", "auto"):
        return value
    return None


def _has_explicit_transport_setting(settings: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(settings, dict):
        return False
    return "transport" in settings


def _resolve_aliased_param_value(
    sources: List[Optional[Dict[str, Any]]],
    snake_key: str,
    camel_key: str,
) -> Any:
    """Pick the first defined value across the given sources, in order.

    Mirrors :func:`resolveAliasedParamValue` (``extra-params.ts``).
    """
    for src in sources:
        if not isinstance(src, dict):
            continue
        if camel_key in src and src[camel_key] is not None:
            return src[camel_key]
        if snake_key in src and src[snake_key] is not None:
            return src[snake_key]
    return None


def _resolve_aliased_param_value_from_keys(
    sources: List[Optional[Dict[str, Any]]],
    keys: List[str],
) -> Any:
    for src in sources:
        if not isinstance(src, dict):
            continue
        for k in keys:
            if k in src and src[k] is not None:
                return src[k]
    return None


def _canonicalize_max_tokens_param(
    merged: Dict[str, Any],
    sources: List[Optional[Dict[str, Any]]],
) -> None:
    """Resolve max_tokens/maxTokens/MaxTokens across sources into ``merged``.

    Mirrors :func:`canonicalizeMaxTokensParam` (``extra-params.ts``).
    """
    for key in ("maxTokens", "max_tokens", "MaxTokens"):
        for src in sources:
            if not isinstance(src, dict):
                continue
            if key in src and src[key] is not None:
                merged["maxTokens"] = src[key]
                if "max_tokens" in merged:
                    del merged["max_tokens"]
                if "MaxTokens" in merged:
                    del merged["MaxTokens"]
                return
    if "max_tokens" in merged:
        merged["maxTokens"] = merged.pop("max_tokens")
    elif "MaxTokens" in merged:
        merged["maxTokens"] = merged.pop("MaxTokens")


def _canonicalize_openrouter_response_cache_params(
    merged: Dict[str, Any],
    sources: List[Optional[Dict[str, Any]]],
) -> None:
    for key in ("openrouterCacheControl", "openrouter_cache_control"):
        resolved = _resolve_aliased_param_value_from_keys(sources, [key])
        if resolved is not None:
            merged["openrouterCacheControl"] = resolved
            merged.pop("openrouter_cache_control", None)
            return


def _should_apply_default_openai_gpt_runtime_params(
    provider: str, model_id: str
) -> bool:
    if provider != "openai":
        return False
    mid = (model_id or "").lower()
    return mid.startswith("gpt-5.") or mid.startswith("gpt-5-") or mid == "gpt-5"


def _apply_default_openai_gpt_runtime_params(
    provider: str, model_id: str, merged: Dict[str, Any]
) -> None:
    if not _should_apply_default_openai_gpt_runtime_params(provider, model_id):
        return
    if "parallel_tool_calls" not in merged and "parallelToolCalls" not in merged:
        merged["parallel_tool_calls"] = True
    if "text_verbosity" not in merged and "textVerbosity" not in merged:
        merged["text_verbosity"] = "low"


def _resolve_model_extra_param_sources(
    cfg: Any, provider: str, model_id: str, agent_id: Optional[str] = None
) -> Dict[str, Any]:
    """Lightweight stand-in for OpenClaw's :func:`resolveModelExtraParamSources`.

    The full implementation walks the model registry + agent overrides; the
    focused port returns an empty source map and delegates to the installable
    hook when one is set.
    """
    return {"defaultParams": {}, "modelParams": None, "agentParams": None}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def clear_prepared_extra_params_cache() -> None:
    """Clear the process-local prepared-extra-params cache.

    Mirrors :func:`clearPreparedExtraParamsCache` (``extra-params.ts``).
    """
    _prepared_extra_params_cache.clear()


def set_provider_runtime_deps_for_test(
    deps: Optional[Dict[str, Any]] = None,
) -> None:
    """Install test-only overrides for the three provider-runtime dependencies.

    Mirrors :func:`setProviderRuntimeDepsForTest` (``extra-params.ts``).
    """
    global _prepare_provider_extra_params_dep, _resolve_provider_extra_params_for_transport_dep, _wrap_provider_stream_fn_dep
    if not deps:
        _prepare_provider_extra_params_dep = None
        _resolve_provider_extra_params_for_transport_dep = None
        _wrap_provider_stream_fn_dep = None
        clear_prepared_extra_params_cache()
        return
    _prepare_provider_extra_params_dep = deps.get("prepareProviderExtraParams")
    _resolve_provider_extra_params_for_transport_dep = deps.get(
        "resolveProviderExtraParamsForTransport"
    )
    _wrap_provider_stream_fn_dep = deps.get("wrapProviderStreamFn")


def reset_provider_runtime_deps_for_test() -> None:
    """Reset the provider-runtime dependencies to defaults.

    Mirrors :func:`resetProviderRuntimeDepsForTest` (``extra-params.ts``).
    """
    set_provider_runtime_deps_for_test(None)


def resolve_extra_params(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Resolve provider-specific extra params from model config.

    Mirrors :func:`resolveExtraParams` (``extra-params.ts``).
    """
    if _resolve_extra_params_hook is not None:
        v = _resolve_extra_params_hook(params)
        return v if v is None or isinstance(v, dict) else None
    sources = _resolve_model_extra_param_sources(
        params.get("cfg"),
        params.get("provider", ""),
        params.get("modelId", ""),
        params.get("agentId"),
    )
    default_params = sources.get("defaultParams") or {}
    model_params = sources.get("modelParams") or {}
    agent_params = sources.get("agentParams") or {}
    global_params = dict(model_params) if model_params else {}
    merged: Dict[str, Any] = {}
    for src in (default_params, global_params, agent_params):
        if isinstance(src, dict):
            merged.update(src)
    resolved_parallel = _resolve_aliased_param_value(
        [default_params, global_params, agent_params],
        "parallel_tool_calls",
        "parallelToolCalls",
    )
    if resolved_parallel is not None:
        merged["parallel_tool_calls"] = resolved_parallel
        merged.pop("parallelToolCalls", None)
    resolved_verbosity = _resolve_aliased_param_value(
        [global_params, agent_params], "text_verbosity", "textVerbosity"
    )
    if resolved_verbosity is not None:
        merged["text_verbosity"] = resolved_verbosity
        merged.pop("textVerbosity", None)
    resolved_response_format = _resolve_aliased_param_value(
        [default_params, global_params, agent_params], "response_format", "responseFormat"
    )
    if resolved_response_format is not None:
        merged["response_format"] = resolved_response_format
        merged.pop("responseFormat", None)
    _canonicalize_max_tokens_param(merged, [default_params, global_params, agent_params])
    resolved_cached_content = _resolve_aliased_param_value(
        [default_params, global_params, agent_params], "cached_content", "cachedContent"
    )
    if resolved_cached_content is not None:
        merged["cachedContent"] = resolved_cached_content
        merged.pop("cached_content", None)
    if params.get("provider") == "openrouter":
        _canonicalize_openrouter_response_cache_params(
            merged, [default_params, global_params, agent_params]
        )
    _apply_default_openai_gpt_runtime_params(
        params.get("provider", ""), params.get("modelId", ""), merged
    )
    return merged if merged else None


def resolve_prepared_extra_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run the provider-runtime prepare/transport hooks on top of resolved extra params.

    Mirrors :func:`resolvePreparedExtraParams` (``extra-params.ts``).
    """
    if _resolve_prepared_extra_params_hook is not None:
        return _resolve_prepared_extra_params_hook(params) or {}
    resolved_extra = params.get("resolvedExtraParams") or resolve_extra_params(
        {
            "cfg": params.get("cfg"),
            "provider": params.get("provider"),
            "modelId": params.get("modelId"),
            "agentId": params.get("agentId"),
        }
    )
    override = params.get("extraParamsOverride")
    if isinstance(override, dict) and override:
        override = _strip_request_scoped_extra_params(
            _sanitize_extra_params_record(
                {k: v for k, v in override.items() if v is not None}
            )
        )
    else:
        override = None
    merged: Dict[str, Any] = {}
    if resolved_extra:
        merged.update(_sanitize_extra_params_record(resolved_extra) or {})
    if override:
        merged.update(override)
    _canonicalize_max_tokens_param(merged, [resolved_extra, override])
    resolved_cached_content = _resolve_aliased_param_value(
        [resolved_extra, override], "cached_content", "cachedContent"
    )
    if resolved_cached_content is not None:
        merged["cachedContent"] = resolved_cached_content
        merged.pop("cached_content", None)
    if params.get("provider") == "openrouter":
        _canonicalize_openrouter_response_cache_params(merged, [resolved_extra, override])
    cfg = params.get("cfg")
    cache_key = None
    if cfg is not None and not _has_function_extra_param_value(params.get("extraParamsOverride")):
        cache_key = _resolve_prepared_extra_params_cache_key(params)
    if cache_key:
        cfg_id = id(cfg)
        bucket = _prepared_extra_params_cache.get(cfg_id)
        if bucket and cache_key in bucket:
            return bucket[cache_key]
    if _prepare_provider_extra_params_dep is not None:
        prepared = _prepare_provider_extra_params_dep(
            {
                "provider": params.get("provider"),
                "config": cfg,
                "workspaceDir": params.get("workspaceDir"),
                "context": {
                    "config": cfg,
                    "agentDir": params.get("agentDir"),
                    "workspaceDir": params.get("workspaceDir"),
                    "provider": params.get("provider"),
                    "modelId": params.get("modelId"),
                    "model": params.get("model"),
                    "extraParams": merged,
                    "thinkingLevel": params.get("thinkingLevel"),
                },
            }
        )
        if not isinstance(prepared, dict):
            prepared = merged
    else:
        prepared = merged
    if _resolve_provider_extra_params_for_transport_dep is not None:
        patch = _resolve_provider_extra_params_for_transport_dep(
            {
                "provider": params.get("provider"),
                "config": cfg,
                "workspaceDir": params.get("workspaceDir"),
                "context": {
                    "config": cfg,
                    "agentDir": params.get("agentDir"),
                    "workspaceDir": params.get("workspaceDir"),
                    "provider": params.get("provider"),
                    "modelId": params.get("modelId"),
                    "extraParams": prepared,
                    "thinkingLevel": params.get("thinkingLevel"),
                    "model": params.get("model"),
                    "transport": params.get("resolvedTransport")
                    or _resolve_supported_transport(prepared.get("transport")),
                },
            }
        )
        if isinstance(patch, dict) and "patch" in patch:
            result: Dict[str, Any] = {**prepared, **patch["patch"]}
        else:
            result = prepared
    else:
        result = prepared
    _canonicalize_max_tokens_param(result, [prepared, None])
    if cache_key is not None and cfg is not None:
        cfg_id = id(cfg)
        bucket = _prepared_extra_params_cache.setdefault(cfg_id, {})
        bucket[cache_key] = result
    return result


def _resolve_prepared_extra_params_cache_key(params: Dict[str, Any]) -> str:
    payload = {
        "provider": params.get("provider", ""),
        "modelId": params.get("modelId", ""),
        "agentId": params.get("agentId", ""),
        "agentDir": params.get("agentDir", ""),
        "workspaceDir": params.get("workspaceDir", ""),
        "thinkingLevel": params.get("thinkingLevel", ""),
        "resolvedTransport": params.get("resolvedTransport", ""),
        "extraParamsOverride": _strip_request_scoped_extra_params(
            _sanitize_extra_params_record(params.get("extraParamsOverride"))
        ),
        "resolvedExtraParams": params.get("resolvedExtraParams"),
        "model": _fingerprint_prepared_extra_params_model(params.get("model")),
    }
    return json.dumps(payload, sort_keys=True, default=str)


def _fingerprint_prepared_extra_params_model(model: Optional[Dict[str, Any]]) -> Any:
    if not isinstance(model, dict):
        return None
    return {
        "api": model.get("api"),
        "provider": model.get("provider"),
        "id": model.get("id"),
        "name": model.get("name"),
        "baseUrl": model.get("baseUrl"),
    }


def resolve_agent_transport_override(params: Dict[str, Any]) -> Optional[str]:
    """Resolve the transport override from settings + extra params.

    Mirrors :func:`resolveAgentTransportOverride` (``extra-params.ts``).
    """
    if _resolve_agent_transport_override_hook is not None:
        v = _resolve_agent_transport_override_hook(params)
        return v
    settings_manager = params.get("settingsManager") if isinstance(params.get("settingsManager"), dict) else None
    if settings_manager is None:
        return None
    get_global = settings_manager.get("getGlobalSettings")
    get_project = settings_manager.get("getProjectSettings")
    global_settings = get_global() if callable(get_global) else None
    project_settings = get_project() if callable(get_project) else None
    if _has_explicit_transport_setting(global_settings) or _has_explicit_transport_setting(project_settings):
        return None
    return _resolve_supported_transport((params.get("effectiveExtraParams") or {}).get("transport"))


def resolve_explicit_settings_transport(params: Dict[str, Any]) -> Optional[str]:
    """Resolve the transport from explicit session settings.

    Mirrors :func:`resolveExplicitSettingsTransport` (``extra-params.ts``).
    """
    if _resolve_explicit_settings_transport_hook is not None:
        v = _resolve_explicit_settings_transport_hook(params)
        return v
    settings_manager = params.get("settingsManager") if isinstance(params.get("settingsManager"), dict) else None
    if settings_manager is None:
        return None
    get_global = settings_manager.get("getGlobalSettings")
    get_project = settings_manager.get("getProjectSettings")
    global_settings = get_global() if callable(get_global) else None
    project_settings = get_project() if callable(get_project) else None
    if not _has_explicit_transport_setting(global_settings) and not _has_explicit_transport_setting(project_settings):
        return None
    return _resolve_supported_transport(params.get("sessionTransport"))


def apply_extra_params_to_agent(
    agent: Any,
    cfg: Any,
    provider: str,
    model_id: str,
    extra_params_override: Optional[Dict[str, Any]] = None,
    thinking_level: Optional[str] = None,
    agent_id: Optional[str] = None,
    workspace_dir: Optional[str] = None,
    model: Optional[Dict[str, Any]] = None,
    agent_dir: Optional[str] = None,
    resolved_transport: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply extra params to an agent's stream function.

    Mirrors :func:`applyExtraParamsToAgent` (``extra-params.ts``).
    """
    if _apply_extra_params_to_agent_hook is not None:
        return _apply_extra_params_to_agent_hook(
            {
                "agent": agent,
                "cfg": cfg,
                "provider": provider,
                "modelId": model_id,
                "extraParamsOverride": extra_params_override,
                "thinkingLevel": thinking_level,
                "agentId": agent_id,
                "workspaceDir": workspace_dir,
                "model": model,
                "agentDir": agent_dir,
                "resolvedTransport": resolved_transport,
                "options": options,
            }
        ) or {"effectiveExtraParams": {}}
    resolved_extra = resolve_extra_params(
        {"cfg": cfg, "provider": provider, "modelId": model_id, "agentId": agent_id}
    )
    if options and isinstance(options, dict) and isinstance(options.get("preparedExtraParams"), dict):
        effective = dict(options["preparedExtraParams"])
    else:
        effective = resolve_prepared_extra_params(
            {
                "cfg": cfg,
                "provider": provider,
                "modelId": model_id,
                "extraParamsOverride": extra_params_override,
                "thinkingLevel": thinking_level,
                "agentId": agent_id,
                "agentDir": agent_dir,
                "workspaceDir": workspace_dir,
                "resolvedExtraParams": resolved_extra,
                "model": model,
                "resolvedTransport": resolved_transport,
            }
        )
    return {"effectiveExtraParams": effective}


__all__ = [
    "REQUEST_SCOPED_EXTRA_PARAM_KEYS",
    "clear_prepared_extra_params_cache",
    "set_provider_runtime_deps_for_test",
    "reset_provider_runtime_deps_for_test",
    "resolve_extra_params",
    "resolve_prepared_extra_params",
    "resolve_agent_transport_override",
    "resolve_explicit_settings_transport",
    "apply_extra_params_to_agent",
    "set_resolve_extra_params_hook",
    "set_resolve_prepared_extra_params_hook",
    "set_resolve_agent_transport_override_hook",
    "set_resolve_explicit_settings_transport_hook",
    "set_apply_extra_params_to_agent_hook",
    "set_prepare_provider_extra_params_dep",
    "set_resolve_provider_extra_params_for_transport_dep",
    "set_wrap_provider_stream_fn_dep",
]
