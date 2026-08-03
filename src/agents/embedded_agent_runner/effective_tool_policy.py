"""jarvis.agents.embedded_agent_runner.effective_tool_policy — final effective tool policy.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/effective-tool-policy.ts``.

Public surface:

- :func:`apply_final_effective_tool_policy`

Phase 7.6h-3 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


_apply_final_effective_tool_policy_hook = None


def set_apply_final_effective_tool_policy_hook(fn) -> None:
    global _apply_final_effective_tool_policy_hook
    _apply_final_effective_tool_policy_hook = fn


def apply_final_effective_tool_policy(params: Dict[str, Any]) -> List[Any]:
    """Apply the final effective tool policy over bundled tools.

    Mirrors :func:`applyFinalEffectiveToolPolicy` (``effective-tool-policy.ts``).
    """
    if _apply_final_effective_tool_policy_hook is not None:
        return _apply_final_effective_tool_policy_hook(params) or []
    bundled = list(params.get("bundledTools") or [])
    if not bundled:
        return bundled
    # The full pipeline runs through the orchestrator's tool policy pipeline; the
    # focused port returns the bundled tools as-is and defers the heavy
    # filtering to the installable runtime hook.
    return bundled


__all__ = [
    "apply_final_effective_tool_policy",
    "set_apply_final_effective_tool_policy_hook",
]
