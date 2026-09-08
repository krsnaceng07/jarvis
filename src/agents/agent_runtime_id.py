"""jarvis.agents.agent_runtime_id — agent runtime id vocabulary.

OpenClaw parity: mirrors ``openclaw-main/src/agents/agent-runtime-id.ts``.

Single canonical home for the embedded-agent runtime id vocabulary.
``src/sessions/agent_harness_session_key.py`` reuses these helpers
instead of carrying its own copy.
"""

from __future__ import annotations

from typing import Any

from src.routing.agent_id import normalize_agent_id as _normalize_agent_id

#: Canonical id of the built-in OpenClaw/JARVIS runtime.
OPENCLAW_AGENT_RUNTIME_ID = "openclaw"
#: Sentinel for "no explicit runtime; resolve from the effective route".
AUTO_AGENT_RUNTIME_ID = "auto"


def normalize_embedded_agent_runtime(raw: str | None) -> str:
    """Normalize a runtime id to the current embedded-agent vocabulary.

    Mirrors ``normalizeEmbeddedAgentRuntime``: empty input collapses to
    ``"openclaw"``; legacy ``"pi"`` and ``"codex-app-server"`` aliases map
    to their current ids. Unrecognized ids pass through trimmed but
    otherwise unchanged.
    """
    value = raw.strip() if isinstance(raw, str) else ""
    if not value:
        return OPENCLAW_AGENT_RUNTIME_ID
    if value == "openclaw" or value == "pi":
        return OPENCLAW_AGENT_RUNTIME_ID
    if value == "auto":
        return AUTO_AGENT_RUNTIME_ID
    if value == "codex-app-server":
        return "codex"
    return value


def normalize_optional_agent_runtime_id(raw: Any) -> str | None:
    """Normalize an optional unknown runtime id; ``None`` when absent/invalid.

    Mirrors ``normalizeOptionalAgentRuntimeId``.
    """
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    return normalize_embedded_agent_runtime(value) if value else None


def resolve_agent_scoped_runtime_override(params: dict[str, Any]) -> str | None:
    """Resolve the deprecated explicit whole-agent runtime override.

    Mirrors ``resolveAgentScopedRuntimeOverride``: reads
    ``agents.<id>.agentRuntime.id``, falling back to
    ``agents.defaults.agentRuntime.id``.
    """
    from src.agents.agent_scope_config import list_agent_entries  # noqa: PLC0415

    cfg = params.get("config")
    agent_id = params.get("agentId")
    agent_runtime: Any = None
    # NOTE: resolve_agent_config() projects entries and drops agentRuntime,
    # so match the raw entry here (mirrors resolveAgentEntry).
    if isinstance(agent_id, str) and agent_id.strip() and isinstance(cfg, dict):
        wanted = _normalize_agent_id(agent_id)
        for entry in list_agent_entries(cfg):
            try:
                if _normalize_agent_id(entry.get("id", "")) != wanted:
                    continue
            except Exception:
                continue
            runtime = entry.get("agentRuntime")
            agent_runtime = runtime.get("id") if isinstance(runtime, dict) else None
            break
    if agent_runtime is None and isinstance(cfg, dict):
        agents = cfg.get("agents")
        defaults = agents.get("defaults") if isinstance(agents, dict) else None
        runtime = defaults.get("agentRuntime") if isinstance(defaults, dict) else None
        agent_runtime = runtime.get("id") if isinstance(runtime, dict) else None
    return normalize_optional_agent_runtime_id(agent_runtime)


def is_default_agent_runtime_id(runtime: str | None) -> bool:
    """Return whether *runtime* means default (implicit) runtime selection.

    Mirrors ``isDefaultAgentRuntimeId``.
    """
    return runtime is None or runtime == AUTO_AGENT_RUNTIME_ID or runtime == "default"


__all__ = [
    "AUTO_AGENT_RUNTIME_ID",
    "OPENCLAW_AGENT_RUNTIME_ID",
    "is_default_agent_runtime_id",
    "normalize_embedded_agent_runtime",
    "normalize_optional_agent_runtime_id",
    "resolve_agent_scoped_runtime_override",
]
