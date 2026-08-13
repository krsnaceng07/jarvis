"""jarvis.agents.embedded_agent_runner.cli_backend_dispatch — opt-in CLI-backend dispatch.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/cli-backend-dispatch.ts``.

Public surface:

- :func:`run_embedded_agent_via_cli_backend_if_eligible`
- :func:`resolve_embedded_cli_backend_dispatch`

Phase 7.6h-4 — focused minimal port.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional


_log = logging.getLogger("agents.embedded_cli_dispatch")


# Installable hooks ---------------------------------------------------------

_run_embedded_agent_via_cli_backend_if_eligible_hook = None
_resolve_embedded_cli_backend_dispatch_hook = None


def set_run_embedded_agent_via_cli_backend_if_eligible_hook(fn) -> None:
    global _run_embedded_agent_via_cli_backend_if_eligible_hook
    _run_embedded_agent_via_cli_backend_if_eligible_hook = fn


def set_resolve_embedded_cli_backend_dispatch_hook(fn) -> None:
    global _resolve_embedded_cli_backend_dispatch_hook
    _resolve_embedded_cli_backend_dispatch_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


ResolveEligibility = Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]


def resolve_embedded_cli_backend_dispatch(
    params: Dict[str, Any],
    *,
    resolve_eligibility: Optional[ResolveEligibility] = None,
) -> Optional[Dict[str, Any]]:
    """Apply the opt-in and transcript-path gates on top of shared eligibility.

    Mirrors :func:`resolveEmbeddedCliBackendDispatch` (``cli-backend-dispatch.ts``).
    """
    if _resolve_embedded_cli_backend_dispatch_hook is not None:
        return _resolve_embedded_cli_backend_dispatch_hook(params)
    if params.get("cliBackendDispatch") != "subscription-auth":
        return None
    session_file = (params.get("sessionFile") or "").strip()
    if not session_file:
        return None
    tools_allow = _resolve_dispatchable_tools_allow(params)
    if not tools_allow:
        return None
    if resolve_eligibility is None:
        # Lazy import to avoid circular import
        try:
            from .cli_backend_dispatch_eligibility import (
                resolve_embedded_cli_backend_dispatch_eligibility,
            )
            resolve_eligibility = resolve_embedded_cli_backend_dispatch_eligibility
        except Exception:
            resolve_eligibility = lambda _p: None
    eligibility = resolve_eligibility(params)
    if not eligibility:
        return None
    return {
        "provider": eligibility["provider"],
        "sessionFile": session_file,
        "toolsAllow": tools_allow,
    }


def _resolve_dispatchable_tools_allow(params: Dict[str, Any]) -> Optional[List[str]]:
    if params.get("disableTools") or params.get("modelRun"):
        return None
    allow = params.get("toolsAllow") or []
    if not allow:
        return None
    seen = set()
    out: List[str] = []
    for name in allow:
        if not isinstance(name, str):
            continue
        normalized = name.strip()
        if not normalized or normalized == "*" or "*" in normalized:
            return None
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out or None


async def run_embedded_agent_via_cli_backend_if_eligible(
    params: Dict[str, Any],
) -> Optional[Any]:
    """Run the embedded turn through the CLI backend when the gate matches.

    Mirrors :func:`runEmbeddedAgentViaCliBackendIfEligible`
    (``cli-backend-dispatch.ts``).
    """
    if _run_embedded_agent_via_cli_backend_if_eligible_hook is not None:
        return _run_embedded_agent_via_cli_backend_if_eligible_hook(params)
    dispatch = resolve_embedded_cli_backend_dispatch(params)
    if not dispatch:
        return None
    # The full CLI dispatch path is heavy and lives in the
    # jarvis_agents.cli_runner plugin; the focused port returns None to let the
    # caller fall through to the native path when no installable hook is set.
    _log.info(
        "cli-backend dispatch eligible: runId=%s provider=%s",
        params.get("runId"),
        dispatch.get("provider"),
    )
    return None


__all__ = [
    "resolve_embedded_cli_backend_dispatch",
    "run_embedded_agent_via_cli_backend_if_eligible",
    "set_run_embedded_agent_via_cli_backend_if_eligible_hook",
    "set_resolve_embedded_cli_backend_dispatch_hook",
]
