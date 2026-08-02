"""jarvis.agents.embedded_agent_runner.run.auth_plan — prepare the embedded-run auth plan.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/auth-plan.ts``.

Public surface:

- :func:`prepare_embedded_run_auth_plan` — assemble the auth profile
  store, scope, and prepared auth attempts for a run.

Phase 7.6b-2 — focused minimal port.

The OpenClaw source is tightly coupled to the
``runtime-plan/prepare-auth`` /
``runtime-plan/credential-scoped-model`` /
``plugins/provider-runtime`` / auth-profile-store layers. The Python
port keeps the public surface and delegates the heavy auth-prep +
materializer logic to installable hooks so the host can plug in the
real layers as they land.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: OpenAI provider id (mirrors ``OPENAI_PROVIDER_ID`` in
#: ``openai-routing.ts``). Reused by the auth-plan scope decision.
OPENAI_PROVIDER_ID: str = "openai"


#: Auth-plan return shape. Mirrors the OpenClaw source's
#: :func:`prepareEmbeddedRunAuthPlan` return value
#: (``auth-plan.ts:201-211``).
EmbeddedRunAuthPlan = Dict[str, Any]


#: Auth-prep attempt shape.
PreparedAgentRuntimeAuthAttempt = Dict[str, Any]


#: Agent harness shape.
AgentHarness = Dict[str, Any]


# ---------------------------------------------------------------------------
# Installable hooks
# ---------------------------------------------------------------------------


#: Hook for :func:`resolveExternalCliAuthOverlayScopeFromSelection` from
#: ``auth-profiles/external-cli-auth-selection.ts``.
_RESOLVE_EXTERNAL_CLI_AUTH_OVERLAY_SCOPE: Callable[[Dict[str, Any]], Dict[str, Any]] = (
    lambda _params: {"ignoreAutoPreferredProfile": False, "providerIds": None}
)


def set_resolve_external_cli_auth_overlay_scope_hook(
    hook: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> None:
    """Install a custom resolveExternalCliAuthOverlayScopeFromSelection hook."""
    global _RESOLVE_EXTERNAL_CLI_AUTH_OVERLAY_SCOPE
    _RESOLVE_EXTERNAL_CLI_AUTH_OVERLAY_SCOPE = hook


#: Hook for :func:`ensureAuthProfileStore` from ``model-auth.ts``.
_ENSURE_AUTH_PROFILE_STORE: Callable[[Dict[str, Any]], Any] = (
    lambda _params: {"version": 1, "profiles": {}}
)


def set_ensure_auth_profile_store_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom ensureAuthProfileStore hook."""
    global _ENSURE_AUTH_PROFILE_STORE
    _ENSURE_AUTH_PROFILE_STORE = hook


#: Hook for :func:`ensureAuthProfileStoreWithoutExternalProfiles` from
#: ``model-auth.ts``.
_ENSURE_AUTH_PROFILE_STORE_WITHOUT_EXTERNAL: Callable[[Dict[str, Any]], Any] = (
    lambda _params: {"version": 1, "profiles": {}}
)


def set_ensure_auth_profile_store_without_external_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom ensureAuthProfileStoreWithoutExternalProfiles hook."""
    global _ENSURE_AUTH_PROFILE_STORE_WITHOUT_EXTERNAL
    _ENSURE_AUTH_PROFILE_STORE_WITHOUT_EXTERNAL = hook


#: Hook for :func:`prepareAgentRuntimeAuth` from
#: ``runtime-plan/prepare-auth.ts``.
_PREPARE_AGENT_RUNTIME_AUTH: Callable[[Dict[str, Any]], Any] = (
    lambda _params: {"attempts": [], "plan": {}}
)


def set_prepare_agent_runtime_auth_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom prepareAgentRuntimeAuth hook."""
    global _PREPARE_AGENT_RUNTIME_AUTH
    _PREPARE_AGENT_RUNTIME_AUTH = hook


#: Hook for the provider-uses-credential-scoped-model check.
_PROVIDER_USES_CREDENTIAL_SCOPED_MODEL_METADATA: Callable[[Dict[str, Any]], bool] = (
    lambda _params: False
)


def set_provider_uses_credential_scoped_model_metadata_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom providerUsesCredentialScopedModelMetadata hook."""
    global _PROVIDER_USES_CREDENTIAL_SCOPED_MODEL_METADATA
    _PROVIDER_USES_CREDENTIAL_SCOPED_MODEL_METADATA = hook


#: Hook for the prepared-runtime-model materializer.
_CREATE_PREPARED_RUNTIME_MODEL_MATERIALIZER: Callable[[Dict[str, Any]], Any] = (
    lambda _params: {
        "materialize": lambda _plan: None,
        "materializeUncached": lambda _plan: None,
    }
)


def set_create_prepared_runtime_model_materializer_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom createPreparedRuntimeModelMaterializer hook."""
    global _CREATE_PREPARED_RUNTIME_MODEL_MATERIALIZER
    _CREATE_PREPARED_RUNTIME_MODEL_MATERIALIZER = hook


#: Hook for the model resolution used by the materializer.
_RESOLVE_MODEL_ASYNC: Callable[..., Awaitable[Any]] = (
    lambda *args, **kwargs: None
)


def set_resolve_model_async_hook(
    hook: Callable[..., Awaitable[Any]],
) -> None:
    """Install a custom resolveModelAsync hook."""
    global _RESOLVE_MODEL_ASYNC
    _RESOLVE_MODEL_ASYNC = hook


#: Hook for the harness selector.
_SELECT_HARNESS_FOR_PREPARED_ATTEMPTS: Callable[
    [Dict[str, Any], List[Dict[str, Any]]], AgentHarness
] = lambda _model, _attempts: {"id": "openclaw", "authBootstrap": None}


def set_select_harness_for_prepared_attempts_hook(
    hook: Callable[[Dict[str, Any], List[Dict[str, Any]]], AgentHarness],
) -> None:
    """Install a custom selectHarnessForPreparedAttempts hook."""
    global _SELECT_HARNESS_FOR_PREPARED_ATTEMPTS
    _SELECT_HARNESS_FOR_PREPARED_ATTEMPTS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_run_auth_plan(
    params: Dict[str, Any],
) -> EmbeddedRunAuthPlan:
    """Assemble the embedded-run auth plan.

    Mirrors :func:`prepareEmbeddedRunAuthPlan` (``auth-plan.ts:24-211``).
    """
    run_params = params.get("runParams") or {}
    provider = params.get("provider") or ""
    model_id = params.get("modelId") or ""
    model = params.get("model") or {}
    agent_dir = params.get("agentDir") or ""
    workspace_dir = params.get("workspaceDir") or ""
    auth_storage = params.get("authStorage")
    model_registry = params.get("modelRegistry")
    mark_stage = params.get("markStage")

    uses_openai_auth_routing = provider == OPENAI_PROVIDER_ID
    initial_harness = params.get("getAgentHarness")() if params.get("getAgentHarness") else {"id": "openclaw"}
    initial_plugin_harness_owns_transport = initial_harness.get("id") != "openclaw"
    openclaw_native_codex_responses_needs_auth_bootstrap = (
        not initial_plugin_harness_owns_transport
        and uses_openai_auth_routing
        and (params.get("getEffectiveModel")() or {}).get("api")
        == "openai-chatgpt-responses"
    )
    if initial_plugin_harness_owns_transport:
        external_cli_auth_scope = {"ignoreAutoPreferredProfile": False, "providerIds": None}
    elif openclaw_native_codex_responses_needs_auth_bootstrap:
        external_cli_auth_scope = {
            "ignoreAutoPreferredProfile": False,
            "providerIds": [OPENAI_PROVIDER_ID],
        }
    else:
        external_cli_auth_scope = _RESOLVE_EXTERNAL_CLI_AUTH_OVERLAY_SCOPE(
            {
                "provider": provider,
                "cfg": run_params.get("config"),
                "agentId": run_params.get("agentId"),
                "modelId": model_id,
                "workspaceDir": workspace_dir,
                "userLockedAuthProfileId": (
                    run_params.get("authProfileId")
                    if run_params.get("authProfileIdSource") == "user"
                    else None
                ),
            }
        )

    no_external_auth_store: Optional[Any] = None
    if not initial_plugin_harness_owns_transport and not external_cli_auth_scope.get("providerIds"):
        no_external_auth_store = _ENSURE_AUTH_PROFILE_STORE_WITHOUT_EXTERNAL(
            {"agentDir": agent_dir, "allowKeychainPrompt": False}
        )
        external_cli_auth_scope = _RESOLVE_EXTERNAL_CLI_AUTH_OVERLAY_SCOPE(
            {
                "provider": provider,
                "cfg": run_params.get("config"),
                "agentId": run_params.get("agentId"),
                "modelId": model_id,
                "workspaceDir": workspace_dir,
                "store": no_external_auth_store,
                "userLockedAuthProfileId": (
                    run_params.get("authProfileId")
                    if run_params.get("authProfileIdSource") == "user"
                    else None
                ),
            }
        )
    if mark_stage:
        mark_stage("scope")

    if uses_openai_auth_routing:
        attempt_auth_profile_store = _ENSURE_AUTH_PROFILE_STORE(
            {
                "agentDir": agent_dir,
                "externalCliProviderIds": [OPENAI_PROVIDER_ID],
                "allowKeychainPrompt": False,
            }
        )
    elif initial_plugin_harness_owns_transport:
        attempt_auth_profile_store = _ENSURE_AUTH_PROFILE_STORE_WITHOUT_EXTERNAL(
            {"agentDir": agent_dir, "allowKeychainPrompt": False}
        )
    elif external_cli_auth_scope.get("providerIds"):
        attempt_auth_profile_store = _ENSURE_AUTH_PROFILE_STORE(
            {
                "agentDir": agent_dir,
                "externalCliProviderIds": external_cli_auth_scope["providerIds"],
                "allowKeychainPrompt": False,
            }
        )
    else:
        attempt_auth_profile_store = (
            no_external_auth_store
            if no_external_auth_store is not None
            else _ENSURE_AUTH_PROFILE_STORE_WITHOUT_EXTERNAL(
                {"agentDir": agent_dir, "allowKeychainPrompt": False}
            )
        )
    if mark_stage:
        mark_stage("store")

    requested_profile_id = (run_params.get("authProfileId") or "").strip() or None
    locked_profile_id = (
        requested_profile_id
        if run_params.get("authProfileIdSource") == "user"
        else None
    )
    preferred_profile_id = (
        None
        if external_cli_auth_scope.get("ignoreAutoPreferredProfile") and not locked_profile_id
        else requested_profile_id
    )
    provider_uses_profile_scoped_model_metadata = (
        _PROVIDER_USES_CREDENTIAL_SCOPED_MODEL_METADATA(
            {
                "provider": provider,
                "modelId": model_id,
                "config": run_params.get("config"),
                "agentDir": agent_dir,
                "workspaceDir": workspace_dir,
            }
        )
    )
    materializer = _CREATE_PREPARED_RUNTIME_MODEL_MATERIALIZER(
        {
            "provider": provider,
            "modelId": model_id,
            "config": run_params.get("config"),
            "getModel": params.get("getRuntimeModel"),
            "nativeModelOwned": bool(params.get("nativeModelOwned", False)),
            "requestedProfileId": run_params.get("authProfileId"),
            "providerUsesProfileScopedModelMetadata": provider_uses_profile_scoped_model_metadata,
            "resolveModel": lambda _ctx: _RESOLVE_MODEL_ASYNC(
                provider,
                model_id,
                agent_dir,
                run_params.get("config"),
                {
                    "authStorage": auth_storage,
                    "modelRegistry": model_registry,
                    "skipAgentDiscovery": True,
                    "allowBundledStaticCatalogFallback": True,
                    "preferBundledStaticCatalogTransport": True,
                    "workspaceDir": workspace_dir,
                },
            ),
        }
    )
    materialize = materializer.get("materialize")
    materialize_uncached = materializer.get("materializeUncached")

    def _create_auth_preparation() -> Dict[str, Any]:
        harness = params.get("getAgentHarness")() if params.get("getAgentHarness") else {"id": "openclaw"}
        return _PREPARE_AGENT_RUNTIME_AUTH(
            {
                "provider": provider,
                "modelId": model_id,
                "modelApi": model.get("api"),
                "modelBaseUrl": model.get("baseUrl"),
                "requestTransportOverrides": params.get("requestStreamTransportOverrides"),
                "config": run_params.get("config"),
                "env": params.get("env"),
                "agentDir": agent_dir,
                "workspaceDir": workspace_dir,
                "authProfileStore": attempt_auth_profile_store,
                "sessionAuthProfileId": preferred_profile_id,
                "sessionAuthProfileSource": run_params.get("authProfileIdSource"),
                "harnessId": harness.get("id"),
                "harnessRuntime": harness.get("id"),
                "harnessAuthBootstrap": harness.get("authBootstrap"),
                "allowHarnessAuthProfileForwarding": True,
                "allowTransientCooldownProbe": run_params.get("allowTransientCooldownProbe") is True,
            }
        )

    resolved_auth_preparation = _create_auth_preparation()
    prepared_auth_attempts = resolved_auth_preparation.get("attempts") or []
    active_prepared_auth_plan = resolved_auth_preparation.get("plan") or {}
    if callable(params.get("applyResolvedRuntimeModel")) and callable(materialize):
        materialized = await _maybe_await(materialize(active_prepared_auth_plan))
        if materialized is not None:
            params["applyResolvedRuntimeModel"](materialized)
    if mark_stage:
        mark_stage("prepare-plan")

    finalized_harness = (
        _SELECT_HARNESS_FOR_PREPARED_ATTEMPTS(
            params.get("getEffectiveModel", lambda: {})(),
            prepared_auth_attempts,
        )
        if params.get("getEffectiveModel")
        else initial_harness
    )
    current_harness = (
        params.get("getAgentHarness")() if params.get("getAgentHarness") else initial_harness
    )
    if finalized_harness.get("id") != current_harness.get("id"):
        if params.get("setAgentHarness"):
            params["setAgentHarness"](finalized_harness)
        resolved_auth_preparation = _create_auth_preparation()
        prepared_auth_attempts = resolved_auth_preparation.get("attempts") or []
        active_prepared_auth_plan = resolved_auth_preparation.get("plan") or {}
        if callable(params.get("applyResolvedRuntimeModel")) and callable(materialize):
            materialized = await _maybe_await(materialize(active_prepared_auth_plan))
            if materialized is not None:
                params["applyResolvedRuntimeModel"](materialized)
        confirmed_harness = (
            _SELECT_HARNESS_FOR_PREPARED_ATTEMPTS(
                params.get("getEffectiveModel", lambda: {})(),
                prepared_auth_attempts,
            )
            if params.get("getEffectiveModel")
            else finalized_harness
        )
        if confirmed_harness.get("id") != (params.get("getAgentHarness")() or {}).get("id"):
            raise RuntimeError(
                f"Prepared auth route did not converge on one agent harness for {provider}/{model_id}."
            )
    if mark_stage:
        mark_stage("harness")

    return {
        "usesOpenAIAuthRouting": uses_openai_auth_routing,
        "attemptAuthProfileStore": attempt_auth_profile_store,
        "lockedProfileId": locked_profile_id,
        "preferredProfileId": preferred_profile_id,
        "providerUsesProfileScopedModelMetadata": provider_uses_profile_scoped_model_metadata,
        "materializeAuthPlan": materialize,
        "materializeAuthPlanUncached": materialize_uncached,
        "preparedAuthAttempts": prepared_auth_attempts,
        "activePreparedAuthPlan": active_prepared_auth_plan,
    }


async def _maybe_await(value: Any) -> Any:
    """Await a value if it's awaitable, otherwise return it as-is."""
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "AgentHarness",
    "EmbeddedRunAuthPlan",
    "OPENAI_PROVIDER_ID",
    "PreparedAgentRuntimeAuthAttempt",
    "prepare_embedded_run_auth_plan",
    "set_create_prepared_runtime_model_materializer_hook",
    "set_ensure_auth_profile_store_hook",
    "set_ensure_auth_profile_store_without_external_hook",
    "set_prepare_agent_runtime_auth_hook",
    "set_provider_uses_credential_scoped_model_metadata_hook",
    "set_resolve_external_cli_auth_overlay_scope_hook",
    "set_resolve_model_async_hook",
    "set_select_harness_for_prepared_attempts_hook",
]
