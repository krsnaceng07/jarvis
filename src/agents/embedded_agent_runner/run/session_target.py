"""jarvis.agents.embedded_agent_runner.run.session_target — session target helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/run-session-target.ts``.

Public surface:

- :func:`apply_agent_run_session_target_identity`
- :func:`resolve_agent_run_session_target`
- :func:`set_resolve_agent_run_session_target_hook`

Phase 7.2+ — focused minimal port.
The Python port keeps the hook shape and the core session-target
identity semantics, while delegating actual storage-backed target
resolution to the host when a hook is installed.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from jarvis_normalization_core.string_coerce import normalize_optional_string
from jarvis_sdk.agent_runtime import resolve_session_agent_id


#: Host-installed session-target resolver hook.
_RESOLVE_AGENT_RUN_SESSION_TARGET_HOOK: Optional[
    Callable[[Dict[str, Any]], Dict[str, Any]]
] = None


def set_resolve_agent_run_session_target_hook(
    hook: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]],
) -> None:
    """Install the host's session-target resolver hook."""
    global _RESOLVE_AGENT_RUN_SESSION_TARGET_HOOK
    _RESOLVE_AGENT_RUN_SESSION_TARGET_HOOK = hook


def apply_agent_run_session_target_identity(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply explicit session-target identity fields.

    Mirrors OpenClaw's ``applyAgentRunSessionTargetIdentity``.
    """
    target = params.get("sessionTarget")
    if not isinstance(target, dict):
        return dict(params)
    return {
        **dict(params),
        "agentId": normalize_optional_string(target.get("agentId")) or params.get("agentId"),
        "sessionId": normalize_optional_string(target.get("sessionId")) or params.get("sessionId"),
        "sessionKey": normalize_optional_string(target.get("sessionKey")) or params.get("sessionKey"),
    }


def resolve_agent_run_session_target(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve the active run session target.

    Mirrors OpenClaw's ``resolveAgentRunSessionTarget``.
    The host hook may provide a rich runtime target; otherwise the
    Python port returns a lightweight fallback target.
    """
    target = params.get("sessionTarget")
    session_key = normalize_optional_string(params.get("sessionKey"))
    session_id = normalize_optional_string(params.get("sessionId"))
    agent_id = normalize_optional_string(
        params.get("agentId")
        or (target.get("agentId") if isinstance(target, dict) else None)
    )

    effective_agent_id = agent_id or resolve_session_agent_id(
        params.get("config"), session_key
    )

    if isinstance(target, dict):
        if not session_key:
            raise ValueError(
                f"Cannot resolve run session target without a session key: {session_id}"
            )
        if _RESOLVE_AGENT_RUN_SESSION_TARGET_HOOK is not None:
            resolved = _RESOLVE_AGENT_RUN_SESSION_TARGET_HOOK(
                {
                    **params,
                    "agentId": effective_agent_id,
                    "sessionKey": session_key,
                }
            )
            if isinstance(resolved, dict):
                return resolved
        return {
            "agentId": effective_agent_id or "",
            "sessionId": session_id,
            "sessionKey": session_key,
            "sessionFile": normalize_optional_string(target.get("sessionFile"))
            or normalize_optional_string(params.get("sessionFile"))
            or "",
            "storePath": normalize_optional_string(target.get("storePath")) or "",
            **(
                {"threadId": target["threadId"]}
                if target.get("threadId") is not None
                else {}
            ),
        }

    session_file = normalize_optional_string(params.get("sessionFile"))
    if session_file:
        return {
            "agentId": effective_agent_id or "",
            "sessionId": session_id,
            "sessionKey": session_key or "",
            "sessionFile": session_file,
        }

    if not session_key:
        raise ValueError(
            f"Cannot resolve run session target without a session key: {session_id}"
        )

    return {
        "agentId": effective_agent_id or "",
        "sessionId": session_id,
        "sessionKey": session_key,
        "sessionFile": "",
    }


__all__ = [
    "apply_agent_run_session_target_identity",
    "resolve_agent_run_session_target",
    "set_resolve_agent_run_session_target_hook",
]
