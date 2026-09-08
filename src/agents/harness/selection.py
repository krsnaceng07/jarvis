"""jarvis.agents.harness.selection — harness availability + selection decisions.

OpenClaw parity: mirrors the decision core of
``openclaw-main/src/agents/harness/selection.ts``
(``selectAgentHarnessDecision``) and
``openclaw-main/src/agents/harness/availability.ts``
(``resolveAgentHarnessAvailabilityDecision``).

Pipeline (same order as OpenClaw):
  configured policy → availability (registered? supports?) → decision.

Decision table:
  - ``openclaw`` / ``auto`` runtime → built-in embedded harness
    (``forced_openclaw`` / ``auto_openclaw``).
  - Explicit (model/provider-scoped) runtime, harness registered and
    supporting the provider → that harness (``forced_plugin``).
  - Explicit runtime, harness registered but provider unsupported →
    declared ``openclaw`` fallback when the harness declares one,
    else ``HarnessNotSupportedError`` (fail closed).
  - Explicit runtime, harness not registered → ``MissingAgentHarnessError``
    (fail closed — "missing harness fails the turn").
  - Implicit ``codex`` runtime, harness missing/unsupported → embedded
    ``openclaw`` (``implicit_plugin_unavailable_openclaw`` /
    ``implicit_plugin_unsupported_openclaw``). Implicit selection never
    fails a turn by itself.

Adaptations: OpenClaw probes live plugin harness objects
(``supports()`` + provider ownership); Jarvis selection takes explicit
``registered_harnesses`` descriptors (``{id, providers?}`` —
``providers=None`` supports every provider) because harness execution
objects live in the owning extensions. The ``openclaw`` built-in is
always available. Planned ``auto`` plugin-candidate search
(``auto_plugin``) collapses to ``auto_openclaw`` until plugin
auto-selection hints exist.
"""

from __future__ import annotations

from typing import Any

from src.agents.agent_runtime_id import (
    is_default_agent_runtime_id,
    normalize_optional_agent_runtime_id,
)
from src.agents.harness.policy import resolve_agent_harness_policy

#: Built-in embedded runtime id. Mirrors the OpenClaw harness id.
OPENCLAW_HARNESS_ID = "openclaw"
#: Codex native harness id. Mirrors ``CODEX_HARNESS_ID``.
CODEX_HARNESS_ID = "codex"


class MissingAgentHarnessError(RuntimeError):
    """Raised when an explicitly required harness is not registered.

    Mirrors ``MissingAgentHarnessError``: ``Requested agent harness
    "<id>" is not registered.``
    """

    def __init__(self, harness_id: str) -> None:
        super().__init__(f'Requested agent harness "{harness_id}" is not registered.')
        self.harness_id = harness_id


class HarnessNotSupportedError(RuntimeError):
    """Raised when a registered harness rejects the provider/model route.

    Mirrors the selection ``does not support`` throw (fail closed unless
    the harness declares an OpenClaw fallback).
    """

    def __init__(self, harness_id: str, provider: str | None, model_id: str | None) -> None:
        ref = f"{provider}/{model_id}" if provider else (model_id or "(unknown model)")
        super().__init__(f'Requested agent harness "{harness_id}" does not support {ref}.')
        self.harness_id = harness_id


def _normalize_provider_id(provider: Any) -> str:
    return provider.strip().lower() if isinstance(provider, str) else ""


def _find_harness(registered: list[dict[str, Any]], harness_id: str) -> dict[str, Any] | None:
    for entry in registered:
        if isinstance(entry, dict) and entry.get("id") == harness_id:
            return entry
    return None


def _harness_supports_provider(harness: dict[str, Any], provider: str) -> bool:
    """Mirror a harness ``supports()`` provider check.

    ``providers=None`` supports every provider (built-in semantics); else
    membership in the descriptor's provider list.
    """
    providers = harness.get("providers")
    if providers is None:
        return True
    if not provider:
        return True
    return provider in [str(p).strip().lower() for p in providers if isinstance(p, str)]


def select_agent_harness(params: dict[str, Any]) -> dict[str, Any]:
    """Select the harness id that owns a turn, or raise fail-closed.

    Mirrors ``selectAgentHarnessDecision``. Returns ``{"harness_id",
    "reason", "policy"}`` where ``reason`` is one of ``forced_openclaw``,
    ``auto_openclaw``, ``forced_plugin``,
    ``implicit_plugin_unavailable_openclaw``,
    ``implicit_plugin_unsupported_openclaw``,
    ``plugin_declared_fallback_openclaw``.

    ``params["registered_harnesses"]`` lists ``{"id", "providers?",
    "fallback?"}`` descriptors; the ``openclaw`` built-in is always
    available and needs no entry.
    """
    policy = resolve_agent_harness_policy(params)
    runtime = policy.get("runtime")
    runtime_source = policy.get("runtimeSource", "implicit")

    pinned = normalize_optional_agent_runtime_id(params.get("agent_harness_id"))
    if pinned and not is_default_agent_runtime_id(pinned):
        # Mirrors availability.ts: the override replaces runtime + source.
        policy = {**policy, "runtime": pinned, "runtimeSource": "model"}
        runtime = pinned
        runtime_source = "model"

    registered = params.get("registered_harnesses") or []
    if not isinstance(registered, list):
        registered = []
    provider = _normalize_provider_id(params.get("provider") or "")
    model_id = params.get("modelId")

    if runtime == OPENCLAW_HARNESS_ID:
        return {"harness_id": OPENCLAW_HARNESS_ID, "reason": "forced_openclaw", "policy": policy}
    if runtime == "auto" or is_default_agent_runtime_id(runtime):
        return {"harness_id": OPENCLAW_HARNESS_ID, "reason": "auto_openclaw", "policy": policy}
    if not isinstance(runtime, str) or not runtime:
        # Unset/non-string runtime cannot name a plugin harness; resolve to
        # the built-in (same outcome as "auto").
        return {"harness_id": OPENCLAW_HARNESS_ID, "reason": "auto_openclaw", "policy": policy}

    implicit = runtime == CODEX_HARNESS_ID and runtime_source == "implicit"
    harness = _find_harness(registered, runtime)
    if harness is None:
        if implicit:
            return {
                "harness_id": OPENCLAW_HARNESS_ID,
                "reason": "implicit_plugin_unavailable_openclaw",
                "policy": {**policy, "runtime": OPENCLAW_HARNESS_ID},
            }
        raise MissingAgentHarnessError(runtime)

    # A pinned native transcript owns early selection; without a prepared
    # provider the owner is not revalidated here. Mirrors selection.ts.
    if pinned == runtime and params.get("prepared_model_provider") is not True:
        return {"harness_id": runtime, "reason": "forced_plugin", "policy": policy}

    if params.get("provider") is None:
        return {"harness_id": runtime, "reason": "forced_plugin", "policy": policy}

    if _harness_supports_provider(harness, provider):
        return {"harness_id": runtime, "reason": "forced_plugin", "policy": policy}
    if implicit or harness.get("fallback") == OPENCLAW_HARNESS_ID:
        return {
            "harness_id": OPENCLAW_HARNESS_ID,
            "reason": "implicit_plugin_unsupported_openclaw"
            if implicit
            else "plugin_declared_fallback_openclaw",
            "policy": {**policy, "runtime": OPENCLAW_HARNESS_ID},
        }
    raise HarnessNotSupportedError(runtime, provider or None, model_id)


def resolve_host_effective_agent_runtime(params: dict[str, Any]) -> str | None:
    """Resolve the concrete harness runtime id that owns the next turn.

    Mirrors ``resolveEffectiveAgentRuntime`` (``thinking-runtime.ts``) in
    projection mode: answers the policy runtime ("openclaw" for ``auto``)
    without failing on unregistered harnesses — fail-closed enforcement
    belongs to selection/execution, not to this probe. Accepts the
    llm-task call shape (``cfg`` or ``config``, ``model`` or ``modelId``);
    returns ``None`` only when no provider/model route is given at all.
    """
    if not isinstance(params, dict):
        return None
    provider = params.get("provider")
    model_id = params.get("modelId", params.get("model"))
    if not isinstance(provider, str) or not provider.strip():
        return None
    cfg = params.get("config", params.get("cfg"))
    policy_params: dict[str, Any] = {
        "provider": provider,
        "config": cfg,
        "env": params.get("env"),
    }
    if isinstance(model_id, str) and model_id.strip():
        policy_params["modelId"] = model_id.strip()
    for key in ("agentId", "sessionKey", "agentScope", "modelApi", "modelBaseUrl"):
        if params.get(key) is not None:
            policy_params[key] = params[key]
    policy = resolve_agent_harness_policy(policy_params)
    runtime = policy.get("runtime")
    if not isinstance(runtime, str) or not runtime or runtime == "auto":
        return OPENCLAW_HARNESS_ID
    return runtime


__all__ = [
    "CODEX_HARNESS_ID",
    "OPENCLAW_HARNESS_ID",
    "HarnessNotSupportedError",
    "MissingAgentHarnessError",
    "resolve_host_effective_agent_runtime",
    "select_agent_harness",
]
