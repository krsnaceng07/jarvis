"""jarvis.agents.embedded_agent_runner.sandbox_info — sandbox/full-access status metadata.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/sandbox-info.ts``.

Public surface:

- :func:`resolve_embedded_full_access_state`
- :func:`resolve_embedded_sandbox_info_exec_policy`
- :func:`build_embedded_sandbox_info`

Phase 7.6h-4 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# Installable hooks ---------------------------------------------------------

_resolve_embedded_full_access_state_hook = None
_resolve_embedded_sandbox_info_exec_policy_hook = None
_build_embedded_sandbox_info_hook = None


def set_resolve_embedded_full_access_state_hook(fn) -> None:
    global _resolve_embedded_full_access_state_hook
    _resolve_embedded_full_access_state_hook = fn


def set_resolve_embedded_sandbox_info_exec_policy_hook(fn) -> None:
    global _resolve_embedded_sandbox_info_exec_policy_hook
    _resolve_embedded_sandbox_info_exec_policy_hook = fn


def set_build_embedded_sandbox_info_hook(fn) -> None:
    global _build_embedded_sandbox_info_hook
    _build_embedded_sandbox_info_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _exec_policy_blocks_full_access(params: Dict[str, Any]) -> bool:
    exec_policy = params.get("execPolicy") or {}
    host_policy = params.get("hostPolicy") or {}
    if exec_policy.get("mode") and exec_policy.get("mode") != "full":
        return True
    if exec_policy.get("security") and exec_policy.get("security") != "full":
        return True
    if exec_policy.get("ask") == "always":
        return True
    if host_policy.get("security") and host_policy.get("security") != "full":
        return True
    if host_policy.get("ask") == "always":
        return True
    return False


def resolve_embedded_full_access_state(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Whether elevated exec can provide full host access for an embedded turn.

    Mirrors :func:`resolveEmbeddedFullAccessState` (``sandbox-info.ts``).
    """
    if _resolve_embedded_full_access_state_hook is not None:
        return _resolve_embedded_full_access_state_hook(params) or {}
    if _exec_policy_blocks_full_access(params):
        return {"available": False, "blockedReason": "host-policy"}
    elevated = params.get("execElevated") or {}
    if elevated.get("fullAccessAvailable") is True:
        return {"available": True}
    if elevated.get("fullAccessAvailable") is False:
        return {
            "available": False,
            "blockedReason": elevated.get("fullAccessBlockedReason") or "host-policy",
        }
    if not elevated.get("enabled") or not elevated.get("allowed"):
        return {"available": False, "blockedReason": "host-policy"}
    return {"available": True}


def resolve_embedded_sandbox_info_exec_policy(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve the effective exec policy for sandbox-info reporting.

    Mirrors :func:`resolveEmbeddedSandboxInfoExecPolicy` (``sandbox-info.ts``).
    """
    if _resolve_embedded_sandbox_info_exec_policy_hook is not None:
        return _resolve_embedded_sandbox_info_exec_policy_hook(params) or {}
    return {
        "mode": "full",
        "security": "full",
        "ask": "off",
    }


def build_embedded_sandbox_info(
    sandbox: Optional[Dict[str, Any]] = None,
    exec_elevated: Optional[Dict[str, Any]] = None,
    exec_policy: Optional[Dict[str, Any]] = None,
    host_policy: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Build the serializable sandbox metadata attached to embedded agent run results.

    Mirrors :func:`buildEmbeddedSandboxInfo` (``sandbox-info.ts``).
    """
    if _build_embedded_sandbox_info_hook is not None:
        v = _build_embedded_sandbox_info_hook(
            {
                "sandbox": sandbox,
                "execElevated": exec_elevated,
                "execPolicy": exec_policy,
                "hostPolicy": host_policy,
            }
        )
        return v if v is None or isinstance(v, dict) else None
    if not sandbox or not sandbox.get("enabled"):
        return None
    elevated_configured = bool(exec_elevated and exec_elevated.get("enabled"))
    elevated_allowed = bool(exec_elevated and exec_elevated.get("enabled") and exec_elevated.get("allowed"))
    full_access = resolve_embedded_full_access_state(
        {
            "execElevated": exec_elevated,
            "execPolicy": exec_policy,
            "hostPolicy": host_policy,
        }
    )
    info: Dict[str, Any] = {
        "enabled": True,
        "workspaceDir": sandbox.get("workspaceDir"),
        "containerWorkspaceDir": sandbox.get("containerWorkdir"),
        "workspaceAccess": sandbox.get("workspaceAccess"),
        "agentWorkspaceMount": "/agent" if sandbox.get("workspaceAccess") == "ro" else None,
        "browserBridgeUrl": (sandbox.get("browser") or {}).get("bridgeUrl")
        if isinstance(sandbox.get("browser"), dict)
        else None,
        "hostBrowserAllowed": bool(sandbox.get("browserAllowHostControl")),
    }
    if elevated_configured:
        info["elevated"] = {
            "allowed": elevated_allowed,
            "defaultLevel": (exec_elevated or {}).get("defaultLevel") or "off",
            "fullAccessAvailable": full_access.get("available", False),
        }
        if full_access.get("blockedReason"):
            info["elevated"]["fullAccessBlockedReason"] = full_access["blockedReason"]
    return info


__all__ = [
    "resolve_embedded_full_access_state",
    "resolve_embedded_sandbox_info_exec_policy",
    "build_embedded_sandbox_info",
    "set_resolve_embedded_full_access_state_hook",
    "set_resolve_embedded_sandbox_info_exec_policy_hook",
    "set_build_embedded_sandbox_info_hook",
]
