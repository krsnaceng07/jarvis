"""jarvis.plugins.provider_claude_thinking — Claude thinking profiles.

OpenClaw parity: mirrors
``openclaw-main/src/plugins/provider-claude-thinking.ts``.

Leaf module for Claude thinking-profile resolution. Kept
dependency-light so auto-reply and the plugin-sdk barrel can both
import without cycling.

The ``ProviderThinkingProfile`` shape is a dict
(``{"levels": [{"id", "label"?, "rank"?}, ...], "defaultLevel"?,
"preserveWhenCatalogReasoningFalse"?}``) — same wire shape as the
profiles exported by :mod:`jarvis_llm.model_contracts`.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from jarvis_llm.model_contracts import (
    CLAUDE_FABLE_5_THINKING_PROFILE,
    CLAUDE_SONNET_5_THINKING_PROFILE,
    resolve_claude_fable5_model_identity,
    resolve_claude_model_identity,
    resolve_claude_mythos5_model_identity,
    resolve_claude_sonnet5_model_identity,
    supports_claude_adaptive_thinking,
    supports_claude_native_xhigh_effort,
)

#: Mirrors ``BASE_CLAUDE_THINKING_LEVELS``
#: (``provider-claude-thinking.ts:16-22``).
BASE_CLAUDE_THINKING_LEVELS: list[dict] = [
    {"id": "off"},
    {"id": "minimal"},
    {"id": "low"},
    {"id": "medium"},
    {"id": "high"},
]


def _ref(model_id: str, params: Optional[dict] = None) -> Any:
    """Build the ``{ id, params }`` model ref the ``jarvis_llm``
    predicates expect (attribute access)."""
    return SimpleNamespace(id=model_id, params=params)


def is_claude_adaptive_thinking_default_model_id(model_id: str) -> bool:
    """Mirrors ``isClaudeAdaptiveThinkingDefaultModelId``
    (``provider-claude-thinking.ts:25-31``)."""
    ref = _ref(model_id)
    return supports_claude_adaptive_thinking(
        ref
    ) and not supports_claude_native_xhigh_effort(ref)


def resolve_claude_thinking_profile(
    model_id: str,
    params: Optional[dict] = None,
    options: Optional[dict] = None,
) -> dict:
    """Mirrors ``resolveClaudeThinkingProfile``
    (``provider-claude-thinking.ts:34-65``)."""
    ref = _ref(model_id, params)
    canonical_model_id = resolve_claude_model_identity(ref)
    if resolve_claude_fable5_model_identity(
        ref
    ) or resolve_claude_mythos5_model_identity(ref):
        return CLAUDE_FABLE_5_THINKING_PROFILE
    if resolve_claude_sonnet5_model_identity(ref):
        return CLAUDE_SONNET_5_THINKING_PROFILE
    if supports_claude_native_xhigh_effort(ref):
        return {
            "levels": [
                *BASE_CLAUDE_THINKING_LEVELS,
                {"id": "xhigh"},
                {"id": "adaptive"},
                {"id": "max"},
            ],
            "defaultLevel": "off",
        }
    if is_claude_adaptive_thinking_default_model_id(canonical_model_id):
        include_native_max = bool(
            options.get("includeNativeMax") if options else False
        )
        return {
            "levels": [
                *BASE_CLAUDE_THINKING_LEVELS,
                {"id": "adaptive"},
                *([{"id": "max"}] if include_native_max else []),
            ],
            "defaultLevel": "adaptive",
        }
    return {"levels": list(BASE_CLAUDE_THINKING_LEVELS)}


__all__ = [
    "BASE_CLAUDE_THINKING_LEVELS",
    "is_claude_adaptive_thinking_default_model_id",
    "resolve_claude_thinking_profile",
]
