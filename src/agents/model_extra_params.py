"""jarvis.agents.model_extra_params — authored provider-request-param detection.

OpenClaw parity: mirrors ``openclaw-main/src/agents/model-extra-params.ts``.

Decides whether embedded OpenClaw would apply *authored* provider request
parameters for a model selection. Recognized native-harness run controls
(``thinking`` / ``fastMode`` / fast-cutoff seconds) do not count as
authored params; anything else does and disqualifies implicit Codex
route selection.
"""

from __future__ import annotations

from typing import Any

from src.auto_reply.thinking import normalize_fast_mode, normalize_think_level
from src.shared.model_key import model_key

#: Model-param keys treated as native fast-mode cutoff controls when their
#: value is a positive integer. Mirrors ``FAST_MODE_CUTOFF_MODEL_PARAM_KEYS``.
FAST_MODE_CUTOFF_MODEL_PARAM_KEYS = frozenset(
    {
        "fastAutoOnSeconds",
        "fastSeconds",
        "fast_auto_on_seconds",
        "fast_seconds",
    }
)


def is_agent_runtime_model_param(key: str, value: Any) -> bool:
    """Return whether a model param is a native harness run control.

    Mirrors ``isAgentRuntimeModelParam``.
    """
    if key == "thinking":
        return (
            value is False
            or value == "disabled"
            or value == "none"
            or (isinstance(value, str) and normalize_think_level(value) is not None)
        )
    if key == "fastMode" or key == "fast_mode":
        # The shared normalizer is typed str|None; non-strings are not
        # valid fast-mode values (matching the TS unknown-input behavior).
        return isinstance(value, str) and normalize_fast_mode(value) is not None
    # NOTE: bool is an int subclass in Python; the TS source requires a
    # number, so booleans are excluded explicitly here.
    return (
        key in FAST_MODE_CUTOFF_MODEL_PARAM_KEYS
        and not isinstance(value, bool)
        and isinstance(value, int)
        and value > 0
    )


def _legacy_model_key(provider: str, model_id: str) -> str | None:
    """Return the raw ``provider/model`` key when it differs from canonical.

    Mirrors ``legacyModelKey``.
    """
    raw_key = f"{provider.strip()}/{model_id.strip()}"
    canonical_key = model_key(provider, model_id)
    return None if raw_key == canonical_key else raw_key


def resolve_model_extra_param_sources(params: dict[str, Any]) -> dict[str, Any]:
    """Resolve the config records merged into one model request.

    Mirrors ``resolveModelExtraParamSources``.
    """
    cfg = params.get("config")
    provider = params.get("provider") or ""
    model_id = params.get("modelId")
    agent_id = params.get("agentId")

    defaults_params = None
    configured_models = None
    if isinstance(cfg, dict):
        agents = cfg.get("agents")
        defaults = agents.get("defaults") if isinstance(agents, dict) else None
        if isinstance(defaults, dict):
            defaults_params = defaults.get("params")
            configured_models = defaults.get("models")

    canonical_key = model_key(provider, model_id) if model_id else None
    legacy_key = (
        _legacy_model_key(provider, model_id) if model_id and isinstance(model_id, str) else None
    )

    def _model_params(models: Any) -> Any:
        if canonical_key is None or not isinstance(models, dict):
            return None
        entry = models.get(canonical_key)
        if isinstance(entry, dict) and entry.get("params") is not None:
            return entry.get("params")
        if legacy_key is not None:
            legacy_entry = models.get(legacy_key)
            if isinstance(legacy_entry, dict):
                return legacy_entry.get("params")
        return None

    model_params = _model_params(configured_models)

    # NOTE: resolve_agent_config() projects entries and drops params, so
    # match the raw entry here (mirrors resolveAgentConfig usage in TS,
    # which returns the full entry).
    agent = None
    if isinstance(agent_id, str) and agent_id.strip() and isinstance(cfg, dict):
        from src.agents.agent_scope_config import list_agent_entries  # noqa: PLC0415
        from src.routing.agent_id import normalize_agent_id  # noqa: PLC0415

        wanted = normalize_agent_id(agent_id)
        for entry in list_agent_entries(cfg):
            if isinstance(entry, dict) and normalize_agent_id(entry.get("id", "")) == wanted:
                agent = entry
                break
    agent_model_params = _model_params(agent.get("models") if isinstance(agent, dict) else None)
    agent_params = agent.get("params") if isinstance(agent, dict) else None
    return {
        "defaultParams": defaults_params,
        "modelParams": model_params,
        "agentModelParams": agent_model_params,
        "agentParams": agent_params,
    }


def has_authored_provider_request_params(params: dict[str, Any]) -> bool:
    """Return whether embedded OpenClaw would apply authored request params.

    Mirrors ``hasAuthoredProviderRequestParams``: any global/agent-level
    ``params`` block counts; model-scoped blocks count unless every entry
    is a native harness run control.
    """
    sources = resolve_model_extra_param_sources(params)
    if any(
        isinstance(source, dict) and len(source) > 0
        for source in (sources.get("defaultParams"), sources.get("agentParams"))
    ):
        return True
    for model_params in (sources.get("modelParams"), sources.get("agentModelParams")):
        if not isinstance(model_params, dict):
            continue
        for key, value in model_params.items():
            if not is_agent_runtime_model_param(key, value):
                return True
    return False


__all__ = [
    "FAST_MODE_CUTOFF_MODEL_PARAM_KEYS",
    "has_authored_provider_request_params",
    "is_agent_runtime_model_param",
    "resolve_model_extra_param_sources",
]
