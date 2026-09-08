"""OpenAI provider-owned thinking policy (cold artifact, no runtime load).

OpenClaw parity: mirrors
``openclaw-main/extensions/openai/thinking-policy.ts``
(``resolveOpenAICodexThinkingProfile``,
``resolveUnifiedOpenAIThinkingProfile``) plus the reasoning-effort table
from ``openclaw-main/extensions/openai/model-route-contract.ts``
(``resolveOpenAICodexReasoningEfforts``).

Ownership: same pattern as ``route_policy.py`` — provider-owned policy,
consumed by core through ``src/plugins/provider_thinking.py`` (mirroring
OpenClaw's ``resolveThinkingProfile`` provider surface). Stdlib only;
route membership helpers are reused from ``.route_policy``.
"""

from __future__ import annotations

from typing import Any

from .route_policy import normalize_openai_model_route_id

#: Canonical OpenAI model ids used by the thinking policy. Mirrors the
#: ``OPENAI_*_MODEL_ID`` constants in ``model-route-contract.ts``.
OPENAI_CHAT_LATEST_MODEL_ID = "chat-latest"
OPENAI_GPT_6_ASTRA_MODEL_ID = "gpt-6-astra"
OPENAI_GPT_56_MODEL_ID = "gpt-5.6"
OPENAI_GPT_56_SOL_MODEL_ID = "gpt-5.6-sol"
OPENAI_GPT_56_TERRA_MODEL_ID = "gpt-5.6-terra"
OPENAI_GPT_56_LUNA_MODEL_ID = "gpt-5.6-luna"
OPENAI_GPT_55_MODEL_ID = "gpt-5.5"
OPENAI_GPT_55_PRO_MODEL_ID = "gpt-5.5-pro"
OPENAI_GPT_54_MODEL_ID = "gpt-5.4"
OPENAI_GPT_54_PRO_MODEL_ID = "gpt-5.4-pro"
OPENAI_GPT_54_MINI_MODEL_ID = "gpt-5.4-mini"
OPENAI_GPT_54_NANO_MODEL_ID = "gpt-5.4-nano"
OPENAI_GPT_53_CODEX_SPARK_MODEL_ID = "gpt-5.3-codex-spark"

#: Codex reasoning-effort order. Mirrors
#: ``OPENAI_CODEX_REASONING_EFFORT_ORDER``.
OPENAI_CODEX_REASONING_EFFORT_ORDER: tuple[str, ...] = (
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
    "ultra",
)

#: Known efforts by model. Mirrors ``OPENAI_CODEX_REASONING_EFFORTS_BY_MODEL``
#: (luna exposes everything except ultra).
_OPENAI_CODEX_REASONING_EFFORTS_BY_MODEL: dict[str, tuple[str, ...]] = {
    OPENAI_GPT_56_SOL_MODEL_ID: OPENAI_CODEX_REASONING_EFFORT_ORDER,
    OPENAI_GPT_56_TERRA_MODEL_ID: OPENAI_CODEX_REASONING_EFFORT_ORDER,
    OPENAI_GPT_56_LUNA_MODEL_ID: OPENAI_CODEX_REASONING_EFFORT_ORDER[:-1],
}

_OPENAI_THINKING_BASE_LEVELS: tuple[str, ...] = ("off", "minimal", "low", "medium", "high")
_OPENAI_THINKING_LEVEL_ORDER: tuple[str, ...] = (
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
    "ultra",
)

#: Models with extra xhigh pickers on Codex turns. Mirrors
#: ``OPENAI_CODEX_XHIGH_MODEL_IDS``.
OPENAI_CODEX_XHIGH_MODEL_IDS: tuple[str, ...] = (
    OPENAI_GPT_56_MODEL_ID,
    OPENAI_GPT_55_MODEL_ID,
    OPENAI_GPT_55_PRO_MODEL_ID,
    OPENAI_GPT_54_MODEL_ID,
    OPENAI_GPT_54_PRO_MODEL_ID,
    OPENAI_GPT_53_CODEX_SPARK_MODEL_ID,
)

#: Unified-surface xhigh models (codex set + mini/nano). Mirrors
#: ``OPENAI_UNIFIED_XHIGH_MODEL_IDS``.
OPENAI_UNIFIED_XHIGH_MODEL_IDS: tuple[str, ...] = (
    *OPENAI_CODEX_XHIGH_MODEL_IDS,
    OPENAI_GPT_54_MINI_MODEL_ID,
    OPENAI_GPT_54_NANO_MODEL_ID,
)


def _normalize(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def resolve_openai_codex_reasoning_efforts(model_id: Any, observed: Any) -> list[str] | None:
    """Merge live Codex observations with first-party capabilities.

    Mirrors ``resolveOpenAICodexReasoningEfforts``: unknown models pass
    observations through; an explicit empty observation stays
    authoritative; partial observations cannot erase known capabilities
    outside the effort order.
    """
    known = _OPENAI_CODEX_REASONING_EFFORTS_BY_MODEL.get(
        normalize_openai_model_route_id(model_id).lower() if isinstance(model_id, str) else ""
    )
    if known is None:
        return list(observed) if isinstance(observed, list) else None
    if not isinstance(observed, list):
        return list(known)
    if len(observed) == 0:
        return []
    normalized_observed = [effort.strip().lower() for effort in observed if isinstance(effort, str)]
    normalized_observed = [effort for effort in normalized_observed if effort]
    # Survivors keep first-seen order (known, then observed): entries outside
    # the effort order survive only when already known. Mirrors the Set
    # delete/filter composition exactly.
    known_set = set(known)
    survivors: list[str] = []
    for effort in [*known, *normalized_observed]:
        if effort in survivors:
            continue
        if effort in OPENAI_CODEX_REASONING_EFFORT_ORDER and effort not in known_set:
            continue
        survivors.append(effort)
    ordered = [effort for effort in OPENAI_CODEX_REASONING_EFFORT_ORDER if effort in survivors]
    rest = [effort for effort in survivors if effort not in ordered]
    return [*ordered, *rest]


def _matches_exact_or_prefix(model_id: str, values: Any) -> bool:
    """Mirror ``matchesExactOrPrefix`` (case-insensitive, prefix allowed)."""
    normalized_id = _normalize(model_id)
    if not isinstance(values, (list, tuple)):
        return False
    for value in values:
        normalized_value = _normalize(value)
        if normalized_value and (
            normalized_id == normalized_value or normalized_id.startswith(normalized_value)
        ):
            return True
    return False


def _normalize_codex_reasoning_effort(value: Any) -> str | None:
    """Mirror ``normalizeCodexReasoningEffort`` (``none`` → ``off``)."""
    normalized = _normalize(value)
    if normalized == "none":
        return "off"
    return normalized if normalized in _OPENAI_THINKING_LEVEL_ORDER else None


def _build_codex_levels(efforts: Any) -> list[dict[str, str]]:
    """Mirror ``buildCodexLevels`` (``off`` always present)."""
    supported: set[str] = {"off"}
    if isinstance(efforts, (list, tuple)):
        for effort in efforts:
            level = _normalize_codex_reasoning_effort(effort)
            if level:
                supported.add(level)
    return [{"id": level} for level in _OPENAI_THINKING_LEVEL_ORDER if level in supported]


def _build_openai_thinking_profile(params: dict[str, Any]) -> dict[str, Any]:
    """Mirror ``buildOpenAIThinkingProfile``."""
    raw_model_id = params.get("modelId", "")
    model_id = (
        normalize_openai_model_route_id(raw_model_id).lower()
        if isinstance(raw_model_id, str)
        else ""
    )
    agent_runtime = _normalize(params.get("agentRuntime"))
    compat_raw = params.get("compat")
    compat: dict[str, Any] = compat_raw if isinstance(compat_raw, dict) else {}
    api = params.get("api")
    xhigh_model_ids = params.get("xhighModelIds") or ()

    if model_id == OPENAI_GPT_6_ASTRA_MODEL_ID:
        codex_efforts = compat.get("supportedReasoningEfforts")
        efforts = [_normalize(e) for e in codex_efforts] if isinstance(codex_efforts, list) else []
        # Ultra is runtime orchestration; the Platform scalar list stops at
        # Max. Preserve narrower account capabilities while exposing the
        # supported runtime mode.
        supports_ultra = agent_runtime in ("openclaw", "codex", "auto") and "max" in efforts
        return {"levels": _build_codex_levels([*efforts, "ultra"] if supports_ultra else efforts)}

    resolved_codex_efforts = (
        resolve_openai_codex_reasoning_efforts(
            raw_model_id, compat.get("supportedReasoningEfforts")
        )
        if api is None or api == "openai-chatgpt-responses"
        else None
    )
    known_codex_efforts = resolve_openai_codex_reasoning_efforts(raw_model_id, None)
    is_gpt56_variant = known_codex_efforts is not None
    codex_supports_max = resolved_codex_efforts or known_codex_efforts or []
    codex_supports_max = "max" in codex_supports_max
    supports_max = model_id.startswith("gpt-5.6") and (
        agent_runtime != "codex" or codex_supports_max
    )
    codex_supports_ultra = "ultra" in (resolved_codex_efforts or known_codex_efforts or [])
    # OpenClaw owns logical Ultra orchestration; native Codex capabilities
    # come from native discovery or the ChatGPT route catalog metadata.
    supports_ultra = (model_id == OPENAI_GPT_56_MODEL_ID or is_gpt56_variant) and (
        agent_runtime in ("openclaw", "auto") or (agent_runtime == "codex" and codex_supports_ultra)
    )
    native_needs_validation = (
        agent_runtime == "codex"
        and compat.get("supportedReasoningEfforts") is None
        and (api is None or api == "openai-chatgpt-responses")
        and not _matches_exact_or_prefix(raw_model_id, xhigh_model_ids)
        and not model_id.startswith("gpt-5.6")
    )
    default_level = "medium" if is_gpt56_variant else None
    levels: list[dict[str, str]] = [{"id": level} for level in _OPENAI_THINKING_BASE_LEVELS]
    if _matches_exact_or_prefix(raw_model_id, xhigh_model_ids):
        levels.append({"id": "xhigh"})
    if supports_max:
        levels.append({"id": "max"})
    if supports_ultra:
        levels.append({"id": "ultra"})
    if native_needs_validation:
        levels.extend([{"id": "xhigh"}, {"id": "max"}])
    if agent_runtime == "codex" and resolved_codex_efforts is not None:
        levels = _build_codex_levels(resolved_codex_efforts)
    profile: dict[str, Any] = {"levels": levels}
    if default_level and any(level["id"] == default_level for level in levels):
        profile["defaultLevel"] = default_level
    return profile


def resolve_openai_codex_thinking_profile(
    model_id: Any,
    agent_runtime: Any = None,
    compat: Any = None,
    api: Any = None,
) -> dict[str, Any]:
    """Mirror ``resolveOpenAICodexThinkingProfile``."""
    return _build_openai_thinking_profile(
        {
            "modelId": model_id,
            "xhighModelIds": OPENAI_CODEX_XHIGH_MODEL_IDS,
            "agentRuntime": agent_runtime,
            "api": api,
            "compat": compat,
        }
    )


def resolve_unified_openai_thinking_profile(
    model_id: Any,
    agent_runtime: Any = None,
    compat: Any = None,
    api: Any = None,
) -> dict[str, Any]:
    """Mirror ``resolveUnifiedOpenAIThinkingProfile``."""
    return _build_openai_thinking_profile(
        {
            "modelId": model_id,
            "xhighModelIds": OPENAI_UNIFIED_XHIGH_MODEL_IDS,
            "agentRuntime": agent_runtime,
            "api": api,
            "compat": compat,
        }
    )


def resolve_thinking_profile(context: Any) -> dict[str, Any] | None:
    """Provider-surface entrypoint. Mirrors ``resolveThinkingProfile`` in
    ``provider-policy-api.ts``: OpenAI provider only, else ``None`` so the
    core falls through to the next surface."""
    if not isinstance(context, dict):
        return None
    provider = context.get("provider")
    if not isinstance(provider, str) or provider.strip().lower() != "openai":
        return None
    return resolve_unified_openai_thinking_profile(
        context.get("modelId"),
        context.get("agentRuntime"),
        context.get("compat"),
        context.get("api"),
    )


__all__ = [
    "OPENAI_CHAT_LATEST_MODEL_ID",
    "OPENAI_CODEX_REASONING_EFFORT_ORDER",
    "OPENAI_CODEX_XHIGH_MODEL_IDS",
    "OPENAI_GPT_53_CODEX_SPARK_MODEL_ID",
    "OPENAI_GPT_54_MINI_MODEL_ID",
    "OPENAI_GPT_54_MODEL_ID",
    "OPENAI_GPT_54_NANO_MODEL_ID",
    "OPENAI_GPT_54_PRO_MODEL_ID",
    "OPENAI_GPT_55_MODEL_ID",
    "OPENAI_GPT_55_PRO_MODEL_ID",
    "OPENAI_GPT_56_LUNA_MODEL_ID",
    "OPENAI_GPT_56_MODEL_ID",
    "OPENAI_GPT_56_SOL_MODEL_ID",
    "OPENAI_GPT_56_TERRA_MODEL_ID",
    "OPENAI_GPT_6_ASTRA_MODEL_ID",
    "OPENAI_UNIFIED_XHIGH_MODEL_IDS",
    "resolve_openai_codex_reasoning_efforts",
    "resolve_openai_codex_thinking_profile",
    "resolve_thinking_profile",
    "resolve_unified_openai_thinking_profile",
]
