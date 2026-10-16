"""jarvis.agents.embedded_agent_runner.run.attempt_tool_catalog — prepare the tool catalog for one attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-tool-catalog.ts``.

Public surface:

- :func:`prepare_embedded_attempt_tool_catalog`

Phase 7.6d-2 — focused minimal port.

The OpenClaw source is tightly coupled to the tool-policy, tool-
filter, tool-allowlist, tool-search, and capability-profile layers.
The Python port keeps the public surface and delegates the heavy
work to installable hooks.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Embedded-attempt tool catalog shape.
EmbeddedAttemptToolCatalog = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the effective-tool-policy step.
_EFFECTIVE_TOOL_POLICY: Callable[[Dict[str, Any]], Any] = lambda _p: None


def set_effective_tool_policy_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom effective-tool-policy hook."""
    global _EFFECTIVE_TOOL_POLICY
    _EFFECTIVE_TOOL_POLICY = hook


#: Hook for the tool-search step.
_TOOL_SEARCH: Callable[[Dict[str, Any]], Any] = lambda _p: {}


def set_tool_search_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom tool-search hook."""
    global _TOOL_SEARCH
    _TOOL_SEARCH = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prepare_embedded_attempt_tool_catalog(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptToolCatalog:
    """Prepare the tool catalog for one attempt.

    Mirrors :func:`prepareEmbeddedAttemptToolCatalog`
    (``attempt-tool-catalog.ts``).
    """
    return {
        "effectiveTools": input_obj.get("effectiveTools") or [],
        "uncompactedEffectiveTools": input_obj.get("uncompactedEffectiveTools") or [],
        "emptyExplicitToolAllowlistError": input_obj.get(
            "emptyExplicitToolAllowlistError"
        ),
        "toolSearch": _TOOL_SEARCH(dict(input_obj or {})),
        "policy": _EFFECTIVE_TOOL_POLICY(dict(input_obj or {})),
    }


__all__ = [
    "EmbeddedAttemptToolCatalog",
    "prepare_embedded_attempt_tool_catalog",
    "set_effective_tool_policy_hook",
    "set_tool_search_hook",
]
