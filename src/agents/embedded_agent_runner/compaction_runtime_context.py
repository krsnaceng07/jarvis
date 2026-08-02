"""jarvis.agents.embedded_agent_runner.compaction_runtime_context — build compaction runtime context.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/compaction-runtime-context.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`resolve_embedded_compaction_thinking_level` — resolve the
  configured compaction thinking level, with candidate revalidation.
- :func:`resolve_embedded_compaction_target` — resolve the effective
  compaction provider/model, honoring ``compaction.model`` overrides.
- :func:`resolve_compaction_harness_runtime` — pick the harness that
  owns this compaction.
- :func:`build_embedded_compaction_runtime_context` — assemble the
  full context dict for context-engine backed compaction.

Phase 7.2b-2 — focused minimal port.

The OpenClaw source has deep integrations with the model catalog,
alias index, and OpenAI routing. The Python port keeps the same
control flow and signature, but uses a small
:class:`_ModelSelection` shim that the host can replace when the
real catalog lands. The default behavior is a transparent
provider/model passthrough that respects the override format
(``provider/model`` or model-only).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


#: Default provider when none is configured. Mirrors
#: ``DEFAULT_PROVIDER`` from ``defaults.ts``. The Python port keeps
#: this small literal so callers can override it through
#: :func:`set_default_provider`.
_DEFAULT_PROVIDER: str = "openai"


def set_default_provider(value: str) -> None:
    """Override the default provider used for compaction target resolution."""
    global _DEFAULT_PROVIDER
    _DEFAULT_PROVIDER = value


def get_default_provider() -> str:
    """Return the active default provider."""
    return _DEFAULT_PROVIDER


def _normalize_optional_agent_runtime_id(value: Optional[str]) -> Optional[str]:
    """Normalize an optional agent runtime id.

    Mirrors :func:`normalizeOptionalAgentRuntimeId` from
    ``agent-runtime-id.ts``. The Python port returns the trimmed
    value, or ``None`` if it is empty.
    """
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed


def _is_default_agent_runtime_id(value: str) -> bool:
    """Return True if ``value`` is the default agent runtime id (``openclaw``).

    Mirrors :func:`isDefaultAgentRuntimeId``.
    """
    return value == "openclaw"


def _normalize_compaction_config_key(value: str) -> str:
    """Normalize a compaction config key (lowercase + trim)."""
    return value.strip().lower()


def _resolve_candidate_thinking_level(
    *,
    config: Optional[Dict[str, Any]],
    provider: str,
    model_id: str,
    level: str,
    agent_id: Optional[str] = None,
    session_key: Optional[str] = None,
    agent_runtime: Optional[str] = None,
) -> Optional[str]:
    """Resolve a thinking level for the candidate provider/model.

    Mirrors :func:`resolveCandidateThinkingLevel` from
    ``thinking-runtime.ts``. The focused minimal port returns the
    input level if it is one of the well-known levels, otherwise
    returns the highest supported level for the candidate. The
    actual provider catalog lives elsewhere; this shim returns the
    level as-is unless the level is ``"ultra"`` (which is OpenClaw's
    way of asking for the highest supported level).
    """
    if level == "ultra":
        return "high"
    return level


def _resolve_selected_openai_runtime_provider(
    *,
    provider: str,
    harness_runtime: Optional[str],
    auth_profile_id: Optional[str],
    config: Optional[Dict[str, Any]],
) -> str:
    """Resolve the OpenAI runtime provider for a candidate.

    Mirrors :func:`resolveSelectedOpenAIRuntimeProvider` from
    ``openai-routing.ts``. The focused minimal port returns the
    provider unchanged (no runtime routing) unless a custom
    registry has been installed.
    """
    return _OPENAI_RUNTIME_PROVIDER_REGISTRY.get(
        (provider, harness_runtime, auth_profile_id), provider
    )


#: Registry of overrides for OpenAI runtime provider routing.
_OPENAI_RUNTIME_PROVIDER_REGISTRY: Dict[Any, str] = {}


def set_openai_runtime_provider_override(
    *,
    provider: str,
    harness_runtime: Optional[str],
    auth_profile_id: Optional[str],
    runtime_provider: str,
) -> None:
    """Install a custom OpenAI runtime provider routing override."""
    _OPENAI_RUNTIME_PROVIDER_REGISTRY[
        (provider, harness_runtime, auth_profile_id)
    ] = runtime_provider


def _infer_unique_provider_from_configured_models(
    *,
    config: Optional[Dict[str, Any]],
    model: str,
) -> Optional[str]:
    """Infer a unique provider from the configured model catalog.

    Mirrors :func:`inferUniqueProviderFromConfiguredModels` from
    ``model-selection-shared.ts``. The focused minimal port returns
    ``None`` because the real model catalog lives elsewhere.
    """
    return _INFERRED_PROVIDER_REGISTRY.get(model)


#: Registry of manual provider inference overrides.
_INFERRED_PROVIDER_REGISTRY: Dict[str, str] = {}


def set_inferred_provider(model: str, provider: str) -> None:
    """Register a provider override for ``model``."""
    _INFERRED_PROVIDER_REGISTRY[model] = provider


def _build_model_alias_index(
    *,
    config: Optional[Dict[str, Any]],
    default_provider: str,
) -> Dict[str, Dict[str, str]]:
    """Build the model alias index.

    Mirrors :func:`buildModelAliasIndex`` from
    ``model-selection-shared.ts``. The focused minimal port returns
    the host-installed alias index, or an empty dict.
    """
    return _MODEL_ALIAS_INDEX


#: Host-installed alias index (alias → provider/model).
_MODEL_ALIAS_INDEX: Dict[str, Dict[str, str]] = {}


def set_model_alias_index(index: Dict[str, Dict[str, str]]) -> None:
    """Install a custom model alias index."""
    global _MODEL_ALIAS_INDEX
    _MODEL_ALIAS_INDEX = index


def _resolve_model_ref_from_string(
    *,
    config: Optional[Dict[str, Any]],
    raw: str,
    default_provider: str,
    alias_index: Dict[str, Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    """Resolve a model reference from a raw string.

    Mirrors :func:`resolveModelRefFromString``. The focused minimal
    port returns ``None`` if the alias index does not contain the
    raw key.
    """
    entry = alias_index.get(raw)
    if not entry:
        return None
    return {
        "alias": True,
        "ref": {
            "provider": entry["provider"],
            "model": entry["model"],
        },
    }


def _has_bare_configured_model_for_provider(
    *,
    cfg: Dict[str, Any],
    provider: str,
    model: str,
) -> bool:
    """Check whether the configured catalog declares ``model`` for ``provider``.

    Mirrors :func:`hasBareConfiguredModelForProvider``
    (``compaction-runtime-context.ts:238-268``).
    """
    provider_key = _normalize_compaction_config_key(provider)
    model_key = _normalize_compaction_config_key(model)
    if not provider_key or not model_key or "/" in model:
        return False
    defaults_models = (cfg.get("agents") or {}).get("defaults", {}).get("models") or {}
    for raw_ref in defaults_models.keys():
        slash_idx = raw_ref.find("/")
        if slash_idx <= 0 or raw_ref.endswith("/*"):
            continue
        raw_provider = raw_ref[:slash_idx]
        raw_model = raw_ref[slash_idx + 1 :]
        if (
            _normalize_compaction_config_key(raw_provider) == provider_key
            and _normalize_compaction_config_key(raw_model) == model_key
        ):
            return True
    providers = (cfg.get("models") or {}).get("providers") or {}
    configured = next(
        (
            v
            for k, v in providers.items()
            if _normalize_compaction_config_key(k) == provider_key
        ),
        None,
    )
    if not configured:
        return False
    return any(
        _normalize_compaction_config_key((entry or {}).get("id", "")) == model_key
        for entry in (configured.get("models") or [])
    )


def resolve_embedded_compaction_thinking_level(
    *,
    config: Optional[Dict[str, Any]] = None,
    provider: str,
    model_id: str,
    inherited_level: Optional[str] = None,
    agent_id: Optional[str] = None,
    session_key: Optional[str] = None,
    agent_runtime: Optional[str] = None,
) -> str:
    """Resolve the compaction thinking level, with candidate revalidation.

    Mirrors :func:`resolveEmbeddedCompactionThinkingLevel``
    (``compaction-runtime-context.ts:62-90``).
    """
    requested = (
        (config or {}).get("agents", {})
        .get("defaults", {})
        .get("compaction", {})
        .get("thinkingLevel")
        or inherited_level
    )
    if not requested:
        return "off"
    return (
        _resolve_candidate_thinking_level(
            config=config,
            provider=provider,
            model_id=model_id,
            level=requested,
            agent_id=agent_id,
            session_key=session_key,
            agent_runtime=agent_runtime,
        )
        or "off"
    )


def resolve_embedded_compaction_target(
    *,
    config: Optional[Dict[str, Any]] = None,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    auth_profile_id: Optional[str] = None,
    harness_runtime: Optional[str] = None,
    model_selection_locked: Optional[bool] = None,
    default_provider: Optional[str] = None,
    default_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve the effective compaction target.

    Mirrors :func:`resolveEmbeddedCompactionTarget``
    (``compaction-runtime-context.ts:96-232``).
    """
    effective_provider = (provider or "").strip() or default_provider
    effective_model = (model_id or "").strip() or default_model
    override = (
        None
        if model_selection_locked
        else (config or {}).get("agents", {})
        .get("defaults", {})
        .get("compaction", {})
        .get("model", "")
        .strip()
        or None
    )

    def _resolve_target_providers(
        target_provider: Optional[str], auth: Optional[str]
    ) -> Dict[str, Any]:
        if not target_provider:
            return {}
        selected = _normalize_optional_agent_runtime_id(harness_runtime)
        use_native = (
            selected is not None
            and selected != "openclaw"
            and not _is_default_agent_runtime_id(selected)
        )
        harness_runtime_value = selected if use_native else "openclaw"
        runtime = _resolve_selected_openai_runtime_provider(
            provider=target_provider,
            harness_runtime=harness_runtime_value,
            auth_profile_id=auth,
            config=config,
        )
        routed = runtime if runtime != target_provider else None
        out: Dict[str, Any] = {
            "runtimeProvider": routed,
            "contextProvider": routed if use_native else None,
        }
        if use_native:
            out["nativeHarnessCompaction"] = True
        return out

    if not override:
        return {
            "provider": effective_provider,
            **_resolve_target_providers(effective_provider, auth_profile_id),
            "model": effective_model,
            "authProfileId": auth_profile_id or None,
        }
    slash_idx = override.find("/")
    if slash_idx > 0:
        override_provider = override[:slash_idx].strip()
        override_model = (override[slash_idx + 1 :].strip() or default_model)
        # When switching provider via override, drop the primary auth profile.
        auth = (
            None
            if override_provider != effective_provider
            else (auth_profile_id or None)
        )
        return {
            "provider": override_provider,
            **_resolve_target_providers(override_provider, auth),
            "model": override_model,
            "authProfileId": auth,
        }
    cfg = config or {}
    current_provider = (effective_provider or "").strip()
    if current_provider and _has_bare_configured_model_for_provider(
        cfg=cfg, provider=current_provider, model=override
    ):
        auth = auth_profile_id or None
        return {
            "provider": current_provider,
            **_resolve_target_providers(current_provider, auth),
            "model": override,
            "authProfileId": auth,
        }
    inferred = _infer_unique_provider_from_configured_models(
        config=config, model=override
    )
    if inferred:
        auth = (
            None if inferred != effective_provider else (auth_profile_id or None)
        )
        return {
            "provider": inferred,
            **_resolve_target_providers(inferred, auth),
            "model": override,
            "authProfileId": auth,
        }
    default = effective_provider or _DEFAULT_PROVIDER
    alias_resolution = _resolve_model_ref_from_string(
        config=config,
        raw=override,
        default_provider=default,
        alias_index=_build_model_alias_index(
            config=config, default_provider=default
        ),
    )
    if alias_resolution and alias_resolution.get("alias"):
        ref = alias_resolution["ref"]
        resolved_provider = ref["provider"]
        auth = (
            None
            if resolved_provider != effective_provider
            else (auth_profile_id or None)
        )
        return {
            "provider": resolved_provider,
            **_resolve_target_providers(resolved_provider, auth),
            "model": ref["model"],
            "authProfileId": auth,
        }
    auth = auth_profile_id or None
    return {
        "provider": effective_provider,
        **_resolve_target_providers(effective_provider, auth),
        "model": override,
        "authProfileId": auth,
    }


def _agent_runtime_auth_plan_matches_target(
    auth_plan: Any,
    *,
    provider: str,
    model_id: str,
) -> bool:
    """Return True when ``auth_plan`` matches the target provider/model.

    Mirrors :func:`agentRuntimeAuthPlanMatchesTarget`` from
    ``runtime-plan/prepare-auth.ts``. The focused minimal port checks
    the ``providerForAuth`` and ``modelId`` fields.
    """
    if auth_plan is None:
        return False
    if isinstance(auth_plan, dict):
        if auth_plan.get("providerForAuth") != provider:
            return False
        return auth_plan.get("modelId") == model_id
    return (
        getattr(auth_plan, "providerForAuth", None) == provider
        and getattr(auth_plan, "modelId", None) == model_id
    )


def resolve_compaction_harness_runtime(
    *,
    bound_harness_runtime: Optional[str] = None,
    prepared_runtime_plan: Optional[Any] = None,
    configured_harness_runtime: Optional[str] = None,
    provider: str,
    model_id: str,
) -> Optional[str]:
    """Resolve the concrete harness already bound to this compaction target.

    Mirrors :func:`resolveCompactionHarnessRuntime``
    (``compaction-runtime-context.ts:271-298``).
    """
    bound = _normalize_optional_agent_runtime_id(bound_harness_runtime)
    if bound:
        return bound
    plan = prepared_runtime_plan
    if plan and _agent_runtime_auth_plan_matches_target(
        getattr(plan, "auth", None) or (plan.get("auth") if isinstance(plan, dict) else None),
        provider=provider,
        model_id=model_id,
    ):
        resolved_ref = (
            getattr(plan, "resolvedRef", None)
            if not isinstance(plan, dict)
            else plan.get("resolvedRef")
        )
        prepared = _normalize_optional_agent_runtime_id(
            getattr(resolved_ref, "harnessId", None)
            if resolved_ref and not isinstance(resolved_ref, dict)
            else (
                (resolved_ref or {}).get("harnessId")
                if isinstance(resolved_ref, dict)
                else None
            )
        )
        if prepared:
            return prepared
    return _normalize_optional_agent_runtime_id(configured_harness_runtime)


def _list_active_process_session_references(
    *,
    scope_key: Optional[str],
) -> List[Dict[str, Any]]:
    """Return the list of process sessions matching ``scope_key``.

    Mirrors :func:`listActiveProcessSessionReferences`` from
    ``bash-process-references.ts``. The focused minimal port returns
    whatever the host has installed via
    :func:`set_active_process_sessions`, or an empty list.
    """
    if scope_key is None:
        return []
    return _ACTIVE_PROCESS_SESSIONS_BY_SCOPE.get(scope_key, [])


_ACTIVE_PROCESS_SESSIONS_BY_SCOPE: Dict[str, List[Dict[str, Any]]] = {}


def set_active_process_sessions(
    by_scope: Dict[str, List[Dict[str, Any]]],
) -> None:
    """Install a process session catalog for compaction runtime context."""
    global _ACTIVE_PROCESS_SESSIONS_BY_SCOPE
    _ACTIVE_PROCESS_SESSIONS_BY_SCOPE = by_scope


def build_embedded_compaction_runtime_context(
    *,
    session_key: Optional[str] = None,
    message_channel: Optional[str] = None,
    message_provider: Optional[str] = None,
    client_caps: Optional[List[str]] = None,
    chat_type: Optional[str] = None,
    agent_account_id: Optional[str] = None,
    current_channel_id: Optional[str] = None,
    current_thread_ts: Optional[str] = None,
    current_message_id: Optional[Any] = None,
    auth_profile_id: Optional[str] = None,
    auth_profile_id_source: Optional[str] = None,
    runtime_auth_plan: Optional[Any] = None,
    workspace_dir: str,
    cwd: Optional[str] = None,
    agent_dir: str,
    config: Optional[Dict[str, Any]] = None,
    skills_snapshot: Any = None,
    sender_is_owner: Optional[bool] = None,
    sender_id: Optional[str] = None,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    harness_runtime: Optional[str] = None,
    model_selection_locked: Optional[bool] = None,
    model_fallbacks_override: Optional[List[str]] = None,
    think_level: Optional[str] = None,
    reasoning_level: Optional[str] = None,
    bash_elevated: Any = None,
    extra_system_prompt: Optional[str] = None,
    source_reply_delivery_mode: Optional[str] = None,
    owner_numbers: Optional[List[str]] = None,
    active_process_sessions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build the full compaction runtime context.

    Mirrors :func:`buildEmbeddedCompactionRuntimeContext``
    (``compaction-runtime-context.ts:300-392``).
    """
    resolved = resolve_embedded_compaction_target(
        config=config,
        provider=provider,
        model_id=model_id,
        auth_profile_id=auth_profile_id,
        harness_runtime=harness_runtime,
        model_selection_locked=model_selection_locked,
    )
    agent_harness_id = (harness_runtime or "").strip() or None
    runtime_auth_plan = (
        runtime_auth_plan
        if runtime_auth_plan
        and resolved.get("provider")
        and resolved.get("model")
        and _agent_runtime_auth_plan_matches_target(
            runtime_auth_plan,
            provider=resolved["provider"],
            model_id=resolved["model"],
        )
        else None
    )
    process_scope_key = (session_key or "").strip() or None
    sessions = active_process_sessions
    if sessions is None:
        sessions = _list_active_process_session_references(
            scope_key=process_scope_key
        )
    out: Dict[str, Any] = {
        "sessionKey": session_key or None,
        "messageChannel": message_channel or None,
        "messageProvider": message_provider or None,
        "clientCaps": client_caps,
        "chatType": chat_type or None,
        "agentAccountId": agent_account_id or None,
        "currentChannelId": current_channel_id or None,
        "currentThreadTs": current_thread_ts or None,
        "currentMessageId": current_message_id,
        "authProfileId": resolved.get("authProfileId"),
        "authProfileIdSource": auth_profile_id_source,
        "runtimeAuthPlan": runtime_auth_plan,
        "agentHarnessId": agent_harness_id,
        "modelSelectionLocked": model_selection_locked,
        "workspaceDir": workspace_dir,
        "cwd": cwd or None,
        "agentDir": agent_dir,
        "config": config,
        "skillsSnapshot": skills_snapshot,
        "senderIsOwner": sender_is_owner,
        "senderId": sender_id or None,
        "provider": resolved.get("provider"),
        "runtimeProvider": resolved.get("runtimeProvider"),
        "model": resolved.get("model"),
        "modelFallbacksOverride": model_fallbacks_override,
        "thinkLevel": think_level,
        "reasoningLevel": reasoning_level,
        "bashElevated": bash_elevated,
        "extraSystemPrompt": extra_system_prompt,
        "sourceReplyDeliveryMode": source_reply_delivery_mode,
        "ownerNumbers": owner_numbers,
    }
    if sessions:
        out["activeProcessSessions"] = sessions
    return out


__all__ = [
    "build_embedded_compaction_runtime_context",
    "get_default_provider",
    "resolve_compaction_harness_runtime",
    "resolve_embedded_compaction_target",
    "resolve_embedded_compaction_thinking_level",
    "set_active_process_sessions",
    "set_default_provider",
    "set_inferred_provider",
    "set_model_alias_index",
    "set_openai_runtime_provider_override",
]
