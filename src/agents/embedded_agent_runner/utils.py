"""jarvis.agents.embedded_agent_runner.utils — small shared normalization helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/utils.ts``.

Public surface:

- :data:`ProviderThinkLevel`
- :func:`normalize_context_token_budget`
- :func:`map_thinking_level_for_provider`
- :func:`map_thinking_level`

Phase 7.6h-3 — focused minimal port.
"""
from __future__ import annotations

import math
from typing import Any, Literal, Optional


# Installable hooks ---------------------------------------------------------

_map_thinking_level_for_provider_hook = None
_map_thinking_level_hook = None
_normalize_context_token_budget_hook = None


def set_map_thinking_level_for_provider_hook(fn) -> None:
    global _map_thinking_level_for_provider_hook
    _map_thinking_level_for_provider_hook = fn


def set_map_thinking_level_hook(fn) -> None:
    global _map_thinking_level_hook
    _map_thinking_level_hook = fn


def set_normalize_context_token_budget_hook(fn) -> None:
    global _normalize_context_token_budget_hook
    _normalize_context_token_budget_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


#: Provider-facing think level (excludes the "ultra" product-only level).
ProviderThinkLevel = Literal["off", "minimal", "low", "medium", "high", "adaptive", "max"]


def normalize_context_token_budget(value: Any) -> Optional[int]:
    """Coerce a value into a positive integer token budget, else ``None``.

    Mirrors :func:`normalizeContextTokenBudget` (``utils.ts``).
    """
    if _normalize_context_token_budget_hook is not None:
        v = _normalize_context_token_budget_hook(value)
        return int(v) if v is not None else None
    if not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return int(math.floor(value))


def map_thinking_level_for_provider(
    level: Optional[str],
) -> Optional[ProviderThinkLevel]:
    """Convert a logical product mode into a provider-facing effort value.

    Mirrors :func:`mapThinkingLevelForProvider` (``utils.ts``).
    """
    if _map_thinking_level_for_provider_hook is not None:
        v = _map_thinking_level_for_provider_hook(level)
        return v  # type: ignore[return-value]
    if level == "ultra":
        return "max"
    if level in ("off", "minimal", "low", "medium", "high", "adaptive", "max"):
        return level  # type: ignore[return-value]
    return None


def map_thinking_level(level: Optional[str]) -> str:
    """Map a product think-level to a runtime ``ThinkingLevel`` value.

    Mirrors :func:`mapThinkingLevel` (``utils.ts``).
    """
    if _map_thinking_level_hook is not None:
        return _map_thinking_level_hook(level) or "off"
    provider_level = map_thinking_level_for_provider(level)
    if not provider_level:
        return "off"
    if provider_level == "adaptive":
        # Runtime does not expose a distinct adaptive level; use Claude's high effort.
        return "high"
    return provider_level


__all__ = [
    "ProviderThinkLevel",
    "normalize_context_token_budget",
    "map_thinking_level_for_provider",
    "map_thinking_level",
    "set_map_thinking_level_for_provider_hook",
    "set_map_thinking_level_hook",
    "set_normalize_context_token_budget_hook",
]
