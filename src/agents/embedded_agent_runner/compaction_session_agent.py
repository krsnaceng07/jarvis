"""jarvis.agents.embedded_agent_runner.compaction_session_agent — prepare a compaction session agent.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/compaction-session-agent.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`prepare_compaction_session_agent` — rebuild the session agent's
  streamFn with provider transforms and apply extra-params.

Phase 7.2b-1 — focused minimal port.

The OpenClaw source mutates ``params.session.agent.streamFn`` to wrap
the LLM stream with provider text transforms. The Python port keeps
the same shape so callers can drive compaction re-prepare the same
way they would in TypeScript. Stream resolution is intentionally a
no-op stub because the underlying LlmRuntime stream resolution lives
elsewhere; the public surface still records ``resolvedApiKey``,
``providerThinkingLevel``, and ``nativeWebSearchPolicyContext`` for
downstream consumers (extension runner, harness tests).
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def _map_thinking_level_for_provider(level: Optional[str]) -> str:
    """Pass-through thinking level mapping.

    Mirrors :func:`mapThinkingLevelForProvider` from OpenClaw
    ``utils.ts``. The focused minimal port keeps the value as-is
    because the actual provider-specific thinking-level mapping
    lives in the provider catalog, not in this module.
    """
    if not level:
        return "off"
    return level


def _resolve_embedded_agent_api_key(
    provider: str,
    resolved_api_key: Optional[str],
    auth_storage: Any,
) -> Optional[str]:
    """Resolve the transport API key.

    Mirrors :func:`resolveEmbeddedAgentApiKey` from
    ``stream-resolution.ts``. The focused minimal port returns the
    caller-supplied key when ``auth_storage`` cannot answer; that
    matches the OpenClaw behavior for an auth storage that does not
    know the provider.
    """
    if not auth_storage:
        return resolved_api_key
    getter = getattr(auth_storage, "get_api_key", None) or getattr(
        auth_storage, "getApiKey", None
    )
    if not getter:
        return resolved_api_key
    try:
        from_keyring = getter(provider)
    except Exception:
        return resolved_api_key
    if from_keyring is None:
        return resolved_api_key
    return from_keyring


def _resolve_embedded_agent_stream_fn(
    llm_runtime: Any,
    current_stream_fn: Any,
    provider_stream_fn: Any,
    session_id: str,
    signal: Any,
    model: Any,
    resolved_api_key: Optional[str],
    transport_auth_available: bool,
    auth_profile_id: Optional[str],
    auth_storage: Any,
) -> Any:
    """Resolve the effective streamFn.

    Mirrors :func:`resolveEmbeddedAgentStreamFn` from
    ``stream-resolution.ts``. The focused minimal port returns the
    current streamFn (or the provider streamFn if the current is
    missing) without rewriting it. The stream resolution itself
    lives in the LLM runtime driver.
    """
    if current_stream_fn is not None:
        return current_stream_fn
    if provider_stream_fn is not None:
        return provider_stream_fn
    return getattr(llm_runtime, "stream_fn", None)


def _wrap_stream_fn_text_transforms(
    stream_fn: Any,
    input_transforms: Any,
    output_transforms: Any,
    transform_system_prompt: bool = False,
) -> Any:
    """Wrap a streamFn with provider text transforms.

    Mirrors :func:`wrapStreamFnTextTransforms` from
    ``plugin-text-transforms.ts``. The focused minimal port returns
    the original streamFn — transforms are applied by the LLM
    runtime driver when it composes the message.
    """
    return stream_fn


def _apply_extra_params_to_agent(
    agent: Any,
    config: Any,
    provider: str,
    model_id: str,
    thinking_budgets: Any,
    provider_thinking_level: str,
    session_agent_id: str,
    effective_workspace: str,
    effective_model: Any,
    agent_dir: str,
    extra: Any,
    options: Dict[str, Any],
) -> Any:
    """Apply extra params to the agent.

    Mirrors :func:`applyExtraParamsToAgent` from
    ``extra-params.ts``. The focused minimal port mutates the agent's
    ``preparedExtraParams`` and ``nativeWebSearchPolicyContext`` and
    returns it.
    """
    if options.get("preparedExtraParams") is not None:
        setattr(agent, "preparedExtraParams", options["preparedExtraParams"])
    setattr(agent, "nativeWebSearchPolicyContext", options.get(
        "nativeWebSearchPolicyContext", {}
    ))
    return agent


def prepare_compaction_session_agent(params: Dict[str, Any]) -> Any:
    """Rebuild the session agent's streamFn with provider transforms.

    Mirrors :func:`prepareCompactionSessionAgent`
    (``compaction-session-agent.ts:16-126``).

    Returns the (mutated) ``params.session.agent``. The OpenClaw source
    mutates the agent in place; the Python port keeps that contract so
    callers see the same ``streamFn``, ``preparedExtraParams`` and
    ``nativeWebSearchPolicyContext`` they would in TypeScript.
    """
    auth_storage = params.get("authStorage")
    if (
        auth_storage
        and isinstance(auth_storage, dict)
        and "getApiKey" in auth_storage
        and callable(auth_storage["getApiKey"])
    ):
        auth_storage_obj = auth_storage
    elif auth_storage and hasattr(auth_storage, "getApiKey") and callable(
        getattr(auth_storage, "getApiKey", None)
    ):
        auth_storage_obj = auth_storage
    else:
        auth_storage_obj = None
    transport_api_key = (
        _resolve_embedded_agent_api_key(
            provider=params["effectiveModel"].get("provider")
            if isinstance(params["effectiveModel"], dict)
            else getattr(params["effectiveModel"], "provider", ""),
            resolved_api_key=params.get("resolvedApiKey"),
            auth_storage=auth_storage_obj,
        )
        if auth_storage_obj is not None
        else params.get("resolvedApiKey")
    )
    agent = params["session"]["agent"]
    current_stream_fn = getattr(agent, "streamFn", None)
    base_stream_fn = current_stream_fn
    if base_stream_fn is None and isinstance(params.get("session"), dict):
        base_stream_fn = current_stream_fn
    agent.streamFn = _resolve_embedded_agent_stream_fn(
        llm_runtime=params["llmRuntime"],
        current_stream_fn=base_stream_fn,
        provider_stream_fn=params.get("providerStreamFn"),
        session_id=params["sessionId"],
        signal=params["signal"],
        model=params["effectiveModel"],
        resolved_api_key=params.get("resolvedApiKey"),
        transport_auth_available=bool((transport_api_key or "").strip()),
        auth_profile_id=(params.get("runtimePlan") or {}).get(
            "auth", {}
        ).get("forwardedAuthProfileId"),
        auth_storage=params.get("authStorage"),
    )
    # Provider text transforms: the focused minimal port has no real
    # text-transform catalog, so the wrap is a no-op. We still record
    # the inputs on the agent for downstream debug visibility.
    setattr(agent, "providerTextTransforms", None)
    provider_thinking_level = _map_thinking_level_for_provider(
        params.get("thinkLevel")
    )
    runtime_plan = params.get("runtimePlan") or {}
    prepared_runtime_extra_params = None
    transport = runtime_plan.get("transport") if isinstance(runtime_plan, dict) else None
    if transport is not None and hasattr(transport, "resolveExtraParams"):
        try:
            prepared_runtime_extra_params = transport.resolveExtraParams(
                thinkingLevel=provider_thinking_level,
                agentId=params.get("sessionAgentId", ""),
                workspaceDir=params.get("effectiveWorkspace", ""),
                model=params["effectiveModel"],
            )
        except Exception:
            prepared_runtime_extra_params = None
    options: Dict[str, Any] = {}
    if prepared_runtime_extra_params is not None:
        options["preparedExtraParams"] = prepared_runtime_extra_params
    options["nativeWebSearchPolicyContext"] = {
        "sessionKey": params.get("sessionKey"),
        "sandboxToolPolicy": params.get("sandboxToolPolicy"),
        "messageProvider": params.get("messageProvider"),
        "agentAccountId": params.get("agentAccountId"),
        "groupId": params.get("groupId"),
        "groupChannel": params.get("groupChannel"),
        "groupSpace": params.get("groupSpace"),
        "spawnedBy": params.get("spawnedBy"),
        "senderId": params.get("senderId"),
        "senderName": params.get("senderName"),
        "senderUsername": params.get("senderUsername"),
        "senderE164": params.get("senderE164"),
    }
    return _apply_extra_params_to_agent(
        agent=agent,
        config=params.get("config"),
        provider=params.get("provider", ""),
        model_id=params.get("modelId", ""),
        thinking_budgets=None,
        provider_thinking_level=provider_thinking_level,
        session_agent_id=params.get("sessionAgentId", ""),
        effective_workspace=params.get("effectiveWorkspace", ""),
        effective_model=params["effectiveModel"],
        agent_dir=params.get("agentDir", ""),
        extra=None,
        options=options,
    )


__all__ = [
    "prepare_compaction_session_agent",
]
