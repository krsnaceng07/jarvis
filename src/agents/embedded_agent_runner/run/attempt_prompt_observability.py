"""jarvis.agents.embedded_agent_runner.run.attempt_prompt_observability — observe an embedded attempt prompt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-prompt-observability.ts``.

Public surface:

- :func:`observe_embedded_attempt_prompt`

Phase 7.6d-2 — focused minimal port.

The OpenClaw source is tightly coupled to the prompt-cache
observability, cache-trace, run-trace, and diagnostic-trace-context
layers. The Python port keeps the public surface and delegates the
heavy work to installable hooks.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


#: Embedded-attempt prompt observation.
EmbeddedAttemptPromptObservation = Dict[str, Any]


#: Prompt-cache change shape.
PromptCacheChange = Dict[str, Any]


#: Prompt-cache break shape.
PromptCacheBreak = Dict[str, Any]


#: Cache trace shape.
CacheTrace = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the recordStage cache-trace step.
_RECORD_STAGE: Callable[[Dict[str, Any]], None] = lambda _p: None


def set_record_stage_attempt_prompt_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom recordStage hook."""
    global _RECORD_STAGE
    _RECORD_STAGE = hook


#: Hook for the prompt-cache-changes step.
_RESOLVE_PROMPT_CACHE_CHANGES: Callable[[Dict[str, Any]], Any] = lambda _p: None


def set_resolve_prompt_cache_changes_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolve-prompt-cache-changes hook."""
    global _RESOLVE_PROMPT_CACHE_CHANGES
    _RESOLVE_PROMPT_CACHE_CHANGES = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def observe_embedded_attempt_prompt(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptPromptObservation:
    """Observe an embedded attempt prompt.

    Mirrors :func:`observeEmbeddedAttemptPrompt`
    (``attempt-prompt-observability.ts``).
    """
    changes: List[PromptCacheChange] = _RESOLVE_PROMPT_CACHE_CHANGES(
        dict(input_obj or {})
    ) or []
    trace: Optional[CacheTrace] = input_obj.get("cacheTrace")
    if trace is not None and changes:
        _RECORD_STAGE(
            {
                "trace": trace,
                "stage": "prompt:observe",
                "options": {"changes": changes},
            }
        )
    return {
        "changes": changes,
        "break": input_obj.get("cacheBreak"),
    }


__all__ = [
    "CacheTrace",
    "EmbeddedAttemptPromptObservation",
    "PromptCacheBreak",
    "PromptCacheChange",
    "observe_embedded_attempt_prompt",
    "set_record_stage_attempt_prompt_hook",
    "set_resolve_prompt_cache_changes_hook",
]
