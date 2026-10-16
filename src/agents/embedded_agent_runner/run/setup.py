"""jarvis.agents.embedded_agent_runner.run.setup — resolve hook-selected model state + pre-model attachments for a run.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/setup.ts``.

Public surface:

- :data:`AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE`
- :data:`AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE`
- :func:`resolve_agent_harness_run_admission_error`
- :func:`resolve_hook_model_selection`
- :func:`build_before_model_resolve_attachments`
- :func:`resolve_native_model_owned_harness_id`
- :func:`create_native_model_owned_runtime_model`
- :func:`resolve_embedded_runtime_model_policy`

Phase 7.6b-2 — focused minimal port.

The OpenClaw source is tightly coupled to the session-entry
``agent-harness-session-key`` policy, hook-runner, provider-runtime,
and context-window-guard layers. The Python port keeps the public
surface and delegates the heavy logic to installable hooks so the
host can plug in the real layers as they land.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


#: Default context tokens. Mirrors :data:`DEFAULT_CONTEXT_TOKENS` from
#: ``defaults.ts``. Used as the fallback when the runtime model has
#: no ``contextWindow`` set.
DEFAULT_CONTEXT_TOKENS: int = 200_000


#: OpenClaw agent runtime id. Mirrors :data:`OPENCLAW_AGENT_RUNTIME_ID`
#: from ``agent-runtime-id.ts``.
OPENCLAW_AGENT_RUNTIME_ID: str = "openclaw"


#: Default agent runtime id. Mirrors :data:`isDefaultAgentRuntimeId`
#: default from ``agent-runtime-id.ts``.
DEFAULT_AGENT_RUNTIME_ID: str = "default"


#: Agent-harness session-id locked error message. Mirrors
#: ``AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE`` from
#: ``agent-harness-session-key.ts``.
AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE: str = (
    "agent harness session is locked to a different identity"
)


#: Agent-harness session-key reserved error message. Mirrors
#: ``AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE`` from
#: ``agent-harness-session-key.ts``.
AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE: str = (
    "agent harness session key is reserved"
)


#: Hook context shape. Mirrors ``HookContext``
#: (``setup.ts:36-44``).
HookContext = Dict[str, Any]


#: Hook-runner shape. Mirrors ``HookRunnerLike``
#: (``setup.ts:46-56``).
HookRunnerLike = Any


#: Context-window info shape.
ContextWindowInfo = Dict[str, Any]


#: Provider runtime model shape.
ProviderRuntimeModel = Dict[str, Any]


# ---------------------------------------------------------------------------
# Installable hooks
# ---------------------------------------------------------------------------


#: Hook for the is-agent-harness-session-key check.
_IS_AGENT_HARNESS_SESSION_KEY: Callable[[Optional[str]], bool] = (
    lambda _key: False
)


def set_is_agent_harness_session_key_hook(
    hook: Callable[[Optional[str]], bool],
) -> None:
    """Install a custom isAgentHarnessSessionKey hook."""
    global _IS_AGENT_HARNESS_SESSION_KEY
    _IS_AGENT_HARNESS_SESSION_KEY = hook


#: Hook for the is-valid-agent-harness-session-store-entry check.
_IS_VALID_AGENT_HARNESS_SESSION_STORE_ENTRY: Callable[
    [Optional[str], Any], bool
] = lambda _key, _entry: False


def set_is_valid_agent_harness_session_store_entry_hook(
    hook: Callable[[Optional[str], Any], bool],
) -> None:
    """Install a custom isValidAgentHarnessSessionStoreEntry hook."""
    global _IS_VALID_AGENT_HARNESS_SESSION_STORE_ENTRY
    _IS_VALID_AGENT_HARNESS_SESSION_STORE_ENTRY = hook


#: Hook for the resolve-agent-harness-session-store-entry-error.
_RESOLVE_AGENT_HARNESS_SESSION_STORE_ENTRY_ERROR: Callable[
    [Optional[str], Any], Optional[str]
] = lambda _key, _entry: None


def set_resolve_agent_harness_session_store_entry_error_hook(
    hook: Callable[[Optional[str], Any], Optional[str]],
) -> None:
    """Install a custom resolveAgentHarnessSessionStoreEntryError hook."""
    global _RESOLVE_AGENT_HARNESS_SESSION_STORE_ENTRY_ERROR
    _RESOLVE_AGENT_HARNESS_SESSION_STORE_ENTRY_ERROR = hook


#: Hook for the normalize-optional-agent-runtime-id.
_NORMALIZE_OPTIONAL_AGENT_RUNTIME_ID: Callable[[Optional[str]], Optional[str]] = (
    lambda value: value.strip() if isinstance(value, str) and value.strip() else None
)


def set_normalize_optional_agent_runtime_id_hook(
    hook: Callable[[Optional[str]], Optional[str]],
) -> None:
    """Install a custom normalizeOptionalAgentRuntimeId hook."""
    global _NORMALIZE_OPTIONAL_AGENT_RUNTIME_ID
    _NORMALIZE_OPTIONAL_AGENT_RUNTIME_ID = hook


#: Hook for the is-default-agent-runtime-id check.
_IS_DEFAULT_AGENT_RUNTIME_ID: Callable[[Optional[str]], bool] = lambda value: (
    value == DEFAULT_AGENT_RUNTIME_ID
)


def set_is_default_agent_runtime_id_hook(
    hook: Callable[[Optional[str]], bool],
) -> None:
    """Install a custom isDefaultAgentRuntimeId hook."""
    global _IS_DEFAULT_AGENT_RUNTIME_ID
    _IS_DEFAULT_AGENT_RUNTIME_ID = hook


#: Hook for the resolve-context-window-info step.
_RESOLVE_CONTEXT_WINDOW_INFO: Callable[[Dict[str, Any]], ContextWindowInfo] = (
    lambda _params: {
        "tokens": DEFAULT_CONTEXT_TOKENS,
        "source": "default",
        "referenceTokens": DEFAULT_CONTEXT_TOKENS,
    }
)


def set_resolve_context_window_info_hook(
    hook: Callable[[Dict[str, Any]], ContextWindowInfo],
) -> None:
    """Install a custom resolveContextWindowInfo hook."""
    global _RESOLVE_CONTEXT_WINDOW_INFO
    _RESOLVE_CONTEXT_WINDOW_INFO = hook


#: Hook for the evaluate-context-window-guard step.
_EVALUATE_CONTEXT_WINDOW_GUARD: Callable[[Dict[str, Any]], Dict[str, Any]] = (
    lambda _params: {"shouldBlock": False, "shouldWarn": False, "tokens": 0}
)


def set_evaluate_context_window_guard_hook(
    hook: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> None:
    """Install a custom evaluateContextWindowGuard hook."""
    global _EVALUATE_CONTEXT_WINDOW_GUARD
    _EVALUATE_CONTEXT_WINDOW_GUARD = hook


#: Hook for the format-context-window-warning-message step.
_FORMAT_CONTEXT_WINDOW_WARNING_MESSAGE: Callable[
    [Dict[str, Any]], str
] = lambda _params: ""


def set_format_context_window_warning_message_hook(
    hook: Callable[[Dict[str, Any]], str],
) -> None:
    """Install a custom formatContextWindowWarningMessage hook."""
    global _FORMAT_CONTEXT_WINDOW_WARNING_MESSAGE
    _FORMAT_CONTEXT_WINDOW_WARNING_MESSAGE = hook


#: Hook for the format-context-window-block-message step.
_FORMAT_CONTEXT_WINDOW_BLOCK_MESSAGE: Callable[
    [Dict[str, Any]], str
] = lambda _params: "context window too small"


def set_format_context_window_block_message_hook(
    hook: Callable[[Dict[str, Any]], str],
) -> None:
    """Install a custom formatContextWindowBlockMessage hook."""
    global _FORMAT_CONTEXT_WINDOW_BLOCK_MESSAGE
    _FORMAT_CONTEXT_WINDOW_BLOCK_MESSAGE = hook


#: Hook for the read-agent-model-context-tokens step.
_READ_AGENT_MODEL_CONTEXT_TOKENS: Callable[[Any], Optional[int]] = lambda _m: None


def set_read_agent_model_context_tokens_hook(
    hook: Callable[[Any], Optional[int]],
) -> None:
    """Install a custom readAgentModelContextTokens hook."""
    global _READ_AGENT_MODEL_CONTEXT_TOKENS
    _READ_AGENT_MODEL_CONTEXT_TOKENS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_agent_harness_run_admission_error(
    params: Dict[str, Any],
) -> Optional[str]:
    """Return the admission error for a durable harness session, or None.

    Mirrors :func:`resolveAgentHarnessRunAdmissionError`
    (``setup.ts:59-98``).
    """
    session_key = (params.get("sessionKey") or "").strip() if params.get("sessionKey") else ""
    if not session_key:
        return None
    entry = params.get("entry")
    reserved_key = bool(_IS_AGENT_HARNESS_SESSION_KEY(session_key))
    if not entry:
        return AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE if reserved_key else None
    if entry.get("modelSelectionLocked") is not True:
        return None
    durable_entry_error = _RESOLVE_AGENT_HARNESS_SESSION_STORE_ENTRY_ERROR(
        session_key, entry
    )
    if durable_entry_error:
        return durable_entry_error
    if not _IS_VALID_AGENT_HARNESS_SESSION_STORE_ENTRY(session_key, entry):
        return None
    requested_harness_id = _NORMALIZE_OPTIONAL_AGENT_RUNTIME_ID(
        params.get("agentHarnessId")
    )
    durable_harness_id = _NORMALIZE_OPTIONAL_AGENT_RUNTIME_ID(
        entry.get("agentHarnessId")
    )
    matches_requested_runtime = (
        params.get("modelSelectionLocked") is True
        and requested_harness_id == durable_harness_id
    )
    matches_durable_runtime = (
        entry.get("sessionId") == params.get("sessionId")
        and durable_harness_id is not None
    )
    if matches_requested_runtime and matches_durable_runtime:
        return None
    return (
        AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE
        if reserved_key
        else AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE
    )


async def resolve_hook_model_selection(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve the (provider, model) override from hook inputs.

    Mirrors :func:`resolveHookModelSelection` (``setup.ts:105-171``).
    """
    provider = params.get("provider") or ""
    model_id = params.get("modelId") or ""
    if params.get("modelSelectionLocked") is True:
        return {
            "provider": provider,
            "modelId": model_id,
            "beforeAgentStartResult": None,
        }
    hook_runner = params.get("hookRunner")
    model_resolve_override: Optional[Dict[str, Any]] = None
    before_agent_start_result: Optional[Dict[str, Any]] = None

    if hook_runner is not None and bool(getattr(hook_runner, "hasHooks", lambda _n: False)("before_model_resolve")):
        event: Dict[str, Any] = {"prompt": params.get("prompt") or ""}
        if params.get("attachments"):
            event["attachments"] = params["attachments"]
        try:
            result = await _maybe_await(
                hook_runner.runBeforeModelResolve(event, params.get("hookContext") or {})
            )
            if result:
                model_resolve_override = dict(result)
        except Exception:
            model_resolve_override = None

    if hook_runner is not None and bool(getattr(hook_runner, "hasHooks", lambda _n: False)("before_agent_start")):
        try:
            result = await _maybe_await(
                hook_runner.runBeforeAgentStart(
                    {"prompt": params.get("prompt") or ""},
                    params.get("hookContext") or {},
                )
            )
            if result:
                before_agent_start_result = dict(result)
                model_resolve_override = {
                    "providerOverride": (
                        (model_resolve_override or {}).get("providerOverride")
                        or before_agent_start_result.get("providerOverride")
                    ),
                    "modelOverride": (
                        (model_resolve_override or {}).get("modelOverride")
                        or before_agent_start_result.get("modelOverride")
                    ),
                }
        except Exception:
            pass

    if (model_resolve_override or {}).get("providerOverride"):
        provider = model_resolve_override["providerOverride"]
    if (model_resolve_override or {}).get("modelOverride"):
        model_id = model_resolve_override["modelOverride"]
    return {
        "provider": provider,
        "modelId": model_id,
        "beforeAgentStartResult": before_agent_start_result,
    }


def build_before_model_resolve_attachments(
    images: Optional[List[Any]],
) -> Optional[List[Dict[str, Any]]]:
    """Convert image refs into the minimal attachment shape.

    Mirrors :func:`buildBeforeModelResolveAttachments`
    (``setup.ts:178-188``).
    """
    if not images:
        return None
    attachments: List[Dict[str, Any]] = []
    for img in images:
        if not isinstance(img, dict):
            continue
        attachments.append(
            {"kind": "image", "mimeType": img.get("mimeType")}
        )
    return attachments or None


def resolve_native_model_owned_harness_id(
    params: Dict[str, Any],
) -> Optional[str]:
    """Resolve a pinned non-default harness that owns native model selection.

    Mirrors :func:`resolveNativeModelOwnedHarnessId`
    (``setup.ts:191-210``).
    """
    if params.get("modelSelectionLocked") is not True:
        return None
    requested_harness_id = _NORMALIZE_OPTIONAL_AGENT_RUNTIME_ID(
        params.get("agentHarnessId")
    )
    selected_harness_id = _NORMALIZE_OPTIONAL_AGENT_RUNTIME_ID(
        params.get("selectedHarnessId")
    )
    if (
        not requested_harness_id
        or _IS_DEFAULT_AGENT_RUNTIME_ID(requested_harness_id)
        or requested_harness_id == OPENCLAW_AGENT_RUNTIME_ID
        or requested_harness_id != selected_harness_id
    ):
        return None
    return requested_harness_id


def create_native_model_owned_runtime_model(
    params: Dict[str, Any],
) -> ProviderRuntimeModel:
    """Build structural model metadata for a native-model-owned harness.

    Mirrors :func:`createNativeModelOwnedRuntimeModel`
    (``setup.ts:213-229``).
    """
    provider = params.get("provider") or ""
    model_id = params.get("modelId") or ""
    return {
        "provider": provider,
        "id": model_id,
        "name": model_id,
        "baseUrl": "",
        "api": "openai-responses",
        "reasoning": True,
        "input": ["text", "image"],
        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        "contextWindow": DEFAULT_CONTEXT_TOKENS,
        "maxTokens": DEFAULT_CONTEXT_TOKENS,
    }


def resolve_embedded_runtime_model_policy(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve context-window policy for the selected runtime model.

    Mirrors :func:`resolveEmbeddedRuntimeModelPolicy`
    (``setup.ts:299-...``).
    """
    runtime_model = params.get("runtimeModel") or {}
    if params.get("nativeModelOwned"):
        return {"effectiveModel": dict(runtime_model)}
    provider = params.get("provider") or ""
    model_id = params.get("modelId") or ""
    ctx_info = _RESOLVE_CONTEXT_WINDOW_INFO(
        {
            "cfg": params.get("cfg"),
            "provider": params.get("contextConfigProvider") or provider,
            "modelId": model_id,
            "modelContextTokens": _READ_AGENT_MODEL_CONTEXT_TOKENS(runtime_model),
            "modelContextWindow": runtime_model.get("contextWindow"),
            "defaultTokens": DEFAULT_CONTEXT_TOKENS,
        }
    )
    effective_model = (
        dict(runtime_model, contextWindow=ctx_info.get("tokens"))
        if (ctx_info.get("tokens", 0) < (runtime_model.get("contextWindow") or float("inf")))
        else dict(runtime_model)
    )
    ctx_guard = _EVALUATE_CONTEXT_WINDOW_GUARD({"info": ctx_info})
    runtime_base_url = runtime_model.get("baseUrl")
    if ctx_guard.get("shouldWarn") and ctx_guard.get("shouldWarn") is True:
        _FORMAT_CONTEXT_WINDOW_WARNING_MESSAGE(
            {
                "provider": provider,
                "modelId": model_id,
                "guard": ctx_guard,
                "runtimeBaseUrl": runtime_base_url,
            }
        )
    if ctx_guard.get("shouldBlock") is True:
        message = _FORMAT_CONTEXT_WINDOW_BLOCK_MESSAGE(
            {"guard": ctx_guard, "runtimeBaseUrl": runtime_base_url}
        )
        raise RuntimeError(
            f"context window too small for {provider}/{model_id}: {message}"
        )
    return {
        "contextWindowInfo": ctx_info,
        "contextTokenBudget": ctx_info.get("tokens"),
        "effectiveModel": effective_model,
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE",
    "AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE",
    "ContextWindowInfo",
    "DEFAULT_AGENT_RUNTIME_ID",
    "DEFAULT_CONTEXT_TOKENS",
    "HookContext",
    "HookRunnerLike",
    "OPENCLAW_AGENT_RUNTIME_ID",
    "ProviderRuntimeModel",
    "build_before_model_resolve_attachments",
    "create_native_model_owned_runtime_model",
    "resolve_agent_harness_run_admission_error",
    "resolve_embedded_runtime_model_policy",
    "resolve_hook_model_selection",
    "resolve_native_model_owned_harness_id",
    "set_evaluate_context_window_guard_hook",
    "set_format_context_window_block_message_hook",
    "set_format_context_window_warning_message_hook",
    "set_is_agent_harness_session_key_hook",
    "set_is_default_agent_runtime_id_hook",
    "set_is_valid_agent_harness_session_store_entry_hook",
    "set_normalize_optional_agent_runtime_id_hook",
    "set_read_agent_model_context_tokens_hook",
    "set_resolve_agent_harness_session_store_entry_error_hook",
    "set_resolve_context_window_info_hook",
]
