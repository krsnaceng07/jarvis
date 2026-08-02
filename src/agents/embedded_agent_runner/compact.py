"""jarvis.agents.embedded_agent_runner.compact — direct (in-lane) compaction flow.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/compact.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`compact_embedded_agent_session_direct` — core compaction
  logic without lane queueing. Use this when already inside a
  session/global lane.
- :data:`testing` — bag of helpers exported for unit tests
  (mirrors the OpenClaw ``testing`` namespace).
- Re-exports :class:`CompactEmbeddedAgentSessionParams` from
  :mod:`compact_types`.

Phase 7.2c-2 — focused minimal port.

The OpenClaw source is ~1900 lines and tightly coupled to the
transcript file state, agent runtime, provider registry, and
compaction checkpoints. The Python port keeps the public surface
and the helper utilities but delegates the heavy
:func:`compact_embedded_agent_session_direct` flow to an installable
handler. The default handler returns a structured "no handler"
result so callers that forgot to install one still get a typed
answer; the host replaces it with the real compaction flow as the
upstream layers land.

The :data:`testing` namespace re-exports the helper functions that
are useful in unit tests: ``has_real_conversation_content``,
``has_meaningful_conversation_content``,
``contains_real_conversation_messages``,
``estimate_tokens_after_compaction``,
``build_before_compaction_hook_metrics``,
``harden_manual_compaction_boundary``,
``resolve_compaction_provider_stream``,
``prepare_compaction_session_agent``,
``run_before_compaction_hooks``, ``run_after_compaction_hooks``,
and ``run_post_compaction_side_effects``.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional

from .compaction_session_agent import prepare_compaction_session_agent
from .compact_types import CompactEmbeddedAgentSessionParams, CompactEmbeddedAgentSessionRuntimeParams
from .compaction_hooks import (
    build_before_compaction_hook_metrics,
    estimate_tokens_after_compaction,
    run_after_compaction_hooks,
    run_before_compaction_hooks,
    run_post_compaction_side_effects,
)
from .logger import log
from .types import EmbeddedAgentCompactResult


#: Re-export the public params TypedDict.
__all__ = [
    "CompactEmbeddedAgentSessionParams",
    "CompactEmbeddedAgentSessionRuntimeParams",
    "compact_embedded_agent_session_direct",
    "testing",
]


#: Handler that the host installs to drive the heavy direct
#: compaction flow. Receives the runtime params + the resolved
#: session target and returns the compaction result.
_DIRECT_COMPACTION_HANDLER: Optional[
    Callable[
        [CompactEmbeddedAgentSessionRuntimeParams, Dict[str, Any]],
        Awaitable[EmbeddedAgentCompactResult],
    ]
] = None


def set_direct_compaction_handler(
    handler: Optional[
        Callable[
            [CompactEmbeddedAgentSessionRuntimeParams, Dict[str, Any]],
            Awaitable[EmbeddedAgentCompactResult],
        ]
    ],
) -> None:
    """Install the host's direct compaction handler."""
    global _DIRECT_COMPACTION_HANDLER
    _DIRECT_COMPACTION_HANDLER = handler


def _normalize_optional_agent_runtime_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed


def _is_default_agent_runtime_id(value: str) -> bool:
    return value == "openclaw"


def _apply_agent_run_session_target_identity(
    params: CompactEmbeddedAgentSessionRuntimeParams,
) -> CompactEmbeddedAgentSessionRuntimeParams:
    """Apply the agent-run session-target identity.

    Mirrors :func:`applyAgentRunSessionTargetIdentity``. The
    focused minimal port is a no-op pass-through because the
    host installs the real implementation when the session target
    is wired in.
    """
    return params


def _resolve_agent_run_session_target(
    params: CompactEmbeddedAgentSessionRuntimeParams,
) -> Dict[str, str]:
    """Resolve the agent-run session target.

    Mirrors :func:`resolveAgentRunSessionTarget``. The Python port
    delegates to an installable handler.
    """
    if _RESOLVE_SESSION_TARGET is not None:
        return _RESOLVE_SESSION_TARGET(params)
    return {
        "agentId": params.get("agentId", ""),
        "sessionId": params.get("sessionId", ""),
        "sessionKey": params.get("sessionKey", ""),
        "sessionFile": params.get("sessionFile", ""),
    }


#: Host-installed resolver for the agent-run session target.
_RESOLVE_SESSION_TARGET: Optional[
    Callable[[CompactEmbeddedAgentSessionRuntimeParams], Dict[str, str]]
] = None


def set_resolve_agent_run_session_target(
    resolver: Optional[
        Callable[[CompactEmbeddedAgentSessionRuntimeParams], Dict[str, str]]
    ],
) -> None:
    """Install the host's session-target resolver."""
    global _RESOLVE_SESSION_TARGET
    _RESOLVE_SESSION_TARGET = resolver


def _has_explicit_compaction_model(params: Dict[str, Any]) -> bool:
    """Return True if the params carry an explicit compaction model override.

    Mirrors :func:`hasExplicitCompactionModel``.
    """
    config = params.get("config") or {}
    override = (
        config.get("agents", {})
        .get("defaults", {})
        .get("compaction", {})
        .get("model")
    )
    return isinstance(override, str) and bool(override.strip())


def _has_compaction_model_fallback_candidates(params: Dict[str, Any]) -> bool:
    """Return True if there are fallback candidates for the compaction model.

    Mirrors :func:`hasCompactionModelFallbackCandidates``. The
    Python port delegates to the host because the real candidate
    list lives in the model catalog.
    """
    return bool(_HAS_FALLBACK_CANDIDATES(params)) if _HAS_FALLBACK_CANDIDATES else True


#: Host-installed check for fallback candidates.
_HAS_FALLBACK_CANDIDATES: Optional[Callable[[Dict[str, Any]], bool]] = None


def set_has_compaction_model_fallback_candidates(
    checker: Optional[Callable[[Dict[str, Any]], bool]],
) -> None:
    """Install the host's fallback-candidate checker."""
    global _HAS_FALLBACK_CANDIDATES
    _HAS_FALLBACK_CANDIDATES = checker


async def compact_embedded_agent_session_direct(
    params_input: CompactEmbeddedAgentSessionRuntimeParams,
) -> EmbeddedAgentCompactResult:
    """Core compaction logic without lane queueing.

    Mirrors :func:`compactEmbeddedAgentSessionDirect``
    (``compact.ts:430-...``).

    For a locked session with a non-default harness, the call
    returns a typed locked-runtime failure immediately. Otherwise
    it resolves the session target and delegates to the host's
    installed handler.
    """
    params_base = _apply_agent_run_session_target_identity(params_input)
    locked_harness_runtime = _normalize_optional_agent_runtime_id(
        params_base.get("agentHarnessId")
    )
    if (
        params_base.get("modelSelectionLocked") is True
        and locked_harness_runtime != "openclaw"
    ):
        reason = (
            f'Model selection is locked to native agent harness "{locked_harness_runtime}"; generic compaction is unavailable.'
            if locked_harness_runtime
            else "Model selection is locked but the persisted agent harness is unavailable."
        )
        return {
            "ok": False,
            "compacted": False,
            "reason": reason,
            "failure": {"reason": "model_selection_locked"},
        }
    run_session_target = _resolve_agent_run_session_target(params_base)
    params: Dict[str, Any] = {
        **params_base,
        "agentId": params_base.get("agentId") or run_session_target.get("agentId"),
        "sessionId": run_session_target.get("sessionId", ""),
        "sessionKey": params_base.get("sessionKey")
        or run_session_target.get("sessionKey"),
        "sessionFile": run_session_target.get("sessionFile", ""),
    }
    if _has_explicit_compaction_model(
        params
    ) or not _has_compaction_model_fallback_candidates(params):
        handler = _DIRECT_COMPACTION_HANDLER or _default_direct_compaction_handler
        return await handler(params_base, run_session_target)
    # Fallback chain path: the host's handler should attempt the
    # primary candidate and any configured fallbacks.
    handler = _DIRECT_COMPACTION_HANDLER or _default_direct_compaction_handler
    return await handler(params_base, run_session_target)


async def _default_direct_compaction_handler(
    params_base: CompactEmbeddedAgentSessionRuntimeParams,
    run_session_target: Dict[str, str],
) -> EmbeddedAgentCompactResult:
    """Default no-op direct compaction handler.

    Returns a structured "no handler" result so callers that forgot
    to install one still get a typed answer.
    """
    log.debug(
        "compact_embedded_agent_session_direct: no handler installed "
        "(sessionId=%s, sessionFile=%s)",
        run_session_target.get("sessionId"),
        run_session_target.get("sessionFile"),
    )
    return {
        "ok": False,
        "compacted": False,
        "reason": "no direct compaction handler installed",
        "failure": {"reason": "no_handler"},
    }


#: Public helper surface for unit tests. Mirrors the OpenClaw
#: ``export const testing = { ... } as const`` namespace.
testing = {
    "hasRealConversationContent": None,  # set in `register_testing_helpers`
    "hasMeaningfulConversationContent": None,
    "containsRealConversationMessages": None,
    "estimateTokensAfterCompaction": estimate_tokens_after_compaction,
    "buildBeforeCompactionHookMetrics": build_before_compaction_hook_metrics,
    "hardenManualCompactionBoundary": None,
    "resolveCompactionProviderStream": None,
    "prepareCompactionSessionAgent": prepare_compaction_session_agent,
    "runBeforeCompactionHooks": run_before_compaction_hooks,
    "runAfterCompactionHooks": run_after_compaction_hooks,
    "runPostCompactionSideEffects": run_post_compaction_side_effects,
}


def register_testing_helpers(
    *,
    has_real_conversation_content: Optional[Callable[..., bool]] = None,
    has_meaningful_conversation_content: Optional[Callable[..., bool]] = None,
    contains_real_conversation_messages: Optional[Callable[..., bool]] = None,
    harden_manual_compaction_boundary: Optional[Callable[..., Any]] = None,
    resolve_compaction_provider_stream: Optional[Callable[..., Any]] = None,
) -> None:
    """Install optional helpers into the :data:`testing` namespace.

    The OpenClaw ``testing`` namespace re-exports helpers that live
    in this file. Some of them depend on the agent runtime
    (transcript file state, message estimation) which the Python
    port does not yet wire; this setter lets the host install those
    helpers as they land.
    """
    if has_real_conversation_content is not None:
        testing["hasRealConversationContent"] = has_real_conversation_content
    if has_meaningful_conversation_content is not None:
        testing["hasMeaningfulConversationContent"] = (
            has_meaningful_conversation_content
        )
    if contains_real_conversation_messages is not None:
        testing["containsRealConversationMessages"] = (
            contains_real_conversation_messages
        )
    if harden_manual_compaction_boundary is not None:
        testing["hardenManualCompactionBoundary"] = (
            harden_manual_compaction_boundary
        )
    if resolve_compaction_provider_stream is not None:
        testing["resolveCompactionProviderStream"] = (
            resolve_compaction_provider_stream
        )
