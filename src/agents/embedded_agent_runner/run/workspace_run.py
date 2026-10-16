"""jarvis.agents.embedded_agent_runner.run.workspace_run — run workspace resolution.

OpenClaw parity: mirrors
``openclaw-main/src/agents/workspace-run.ts``.

Phase 7.2+ — focused minimal port.
The Python port keeps the workspace resolution shape and
session-key/agent-id fallback semantics while delegating the
agent workspace path computation to the host runtime.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from jarvis_normalization_core.string_coerce import normalize_optional_string
from jarvis_sdk.agent_runtime import resolve_agent_workspace_dir
from src.routing.agent_scope import resolve_default_agent_id
from src.routing.session_key import (
    classify_session_key_shape,
    normalize_agent_id,
    parse_agent_session_key,
)


def _resolve_user_path(value: str) -> str:
    if not isinstance(value, str):
        return value
    trimmed = value.strip()
    if trimmed.startswith("~"):
        return os.path.expanduser(trimmed)
    return trimmed


def _resolve_run_agent_id(
    session_key: Any,
    agent_id: Any,
    config: Any,
) -> Dict[str, str]:
    session_key_str = normalize_optional_string(session_key)
    agent_id_str = normalize_optional_string(agent_id)
    if session_key_str:
        shape = classify_session_key_shape(session_key_str)
        if shape == "malformed_agent":
            raise ValueError("Malformed agent session key; refusing workspace resolution.")
    if agent_id_str:
        return {
            "agentId": normalize_agent_id(agent_id_str),
            "agentIdSource": "explicit",
        }
    default_agent_id = resolve_default_agent_id(config)
    if not session_key_str or session_key_str == "" or classify_session_key_shape(session_key_str) != "agent":
        return {
            "agentId": default_agent_id,
            "agentIdSource": "default",
        }
    parsed = parse_agent_session_key(session_key_str)
    if parsed and parsed.get("agentId"):
        return {
            "agentId": normalize_agent_id(parsed["agentId"]),
            "agentIdSource": "session_key",
        }
    return {
        "agentId": default_agent_id,
        "agentIdSource": "default",
    }


def resolve_run_workspace_dir(
    workspaceDir: Any,
    sessionKey: Any = None,
    agentId: Any = None,
    config: Any = None,
    env: Any = None,
) -> Dict[str, Any]:
    requested = workspaceDir
    agent_resolution = _resolve_run_agent_id(sessionKey, agentId, config)
    agent_id = agent_resolution["agentId"]
    agent_id_source = agent_resolution["agentIdSource"]

    if isinstance(requested, str):
        trimmed = requested.strip()
        if trimmed:
            return {
                "workspaceDir": _resolve_user_path(trimmed),
                "usedFallback": False,
                "agentId": agent_id,
                "agentIdSource": agent_id_source,
            }

    fallback_reason = (
        "missing"
        if requested is None
        else "blank"
        if isinstance(requested, str)
        else "invalid_type"
    )
    fallback_workspace = resolve_agent_workspace_dir(
        config if isinstance(config, dict) else {}, agent_id
    )
    return {
        "workspaceDir": _resolve_user_path(fallback_workspace),
        "usedFallback": True,
        "fallbackReason": fallback_reason,
        "agentId": agent_id,
        "agentIdSource": agent_id_source,
    }


__all__ = [
    "resolve_run_workspace_dir",
]
