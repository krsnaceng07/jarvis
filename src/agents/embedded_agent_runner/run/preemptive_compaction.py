"""jarvis.agents.embedded_agent_runner.run.preemptive_compaction — estimate prompt pressure and decide pre-prompt compaction routing.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/preemptive-compaction.ts``.

Public surface:

Constants:

- :data:`PREEMPTIVE_OVERFLOW_ERROR_TEXT`
- :data:`ESTIMATED_CHARS_PER_TOKEN`
- :data:`TOOL_RESULT_CHARS_PER_TOKEN`
- :data:`JSON_PAYLOAD_CHARS_PER_TOKEN`
- :data:`MESSAGE_BOUNDARY_OVERHEAD_TOKENS`
- :data:`CONTENT_BLOCK_OVERHEAD_TOKENS`
- :data:`IMAGE_BLOCK_TOKENS`
- :data:`TRUNCATION_ROUTE_BUFFER_TOKENS`

Types:

- :data:`PreemptiveCompactionDecision`
- :data:`LlmBoundaryTokenPressure`

Functions:

- :func:`estimate_llm_boundary_token_pressure`
- :func:`estimate_rendered_llm_boundary_token_pressure`
- :func:`should_preemptively_compact_before_prompt`
- :func:`format_pre_prompt_precheck_log`
- :func:`build_pre_prompt_context_budget_status`

Phase 7.6c-1 — focused minimal port.

The OpenClaw source is tightly coupled to the agent-compaction
constants, the cjk-chars helper, the runtime index exports
(BRANCH_SUMMARY_PREFIX/SUFFIX, COMPACTION_SUMMARY_PREFIX/SUFFIX,
bashExecutionToText), and the
estimateToolResultReductionPotential helper. The Python port keeps
the public surface and delegates the heavy work to installable
hooks so the host can plug in the real layers as they land.
"""
from __future__ import annotations

import json
import math
from typing import Any, Callable, Dict


#: Pre-prompt overflow error text. Mirrors
#: :data:`PREEMPTIVE_OVERFLOW_ERROR_TEXT`
#: (``preemptive-compaction.ts:23-24``).
PREEMPTIVE_OVERFLOW_ERROR_TEXT: str = (
    "Context overflow: prompt too large for the model (precheck)."
)


#: Default chars-per-token estimate. Mirrors
#: :data:`ESTIMATED_CHARS_PER_TOKEN` (``preemptive-compaction.ts:26``).
ESTIMATED_CHARS_PER_TOKEN: int = 4


#: Tool-result chars-per-token estimate. Mirrors
#: :data:`TOOL_RESULT_CHARS_PER_TOKEN` (``preemptive-compaction.ts:27``).
TOOL_RESULT_CHARS_PER_TOKEN: int = 2


#: JSON payload chars-per-token estimate. Mirrors
#: :data:`JSON_PAYLOAD_CHARS_PER_TOKEN` (``preemptive-compaction.ts:28``).
JSON_PAYLOAD_CHARS_PER_TOKEN: int = 3


#: Message boundary overhead tokens. Mirrors
#: :data:`MESSAGE_BOUNDARY_OVERHEAD_TOKENS` (``preemptive-compaction.ts:29``).
MESSAGE_BOUNDARY_OVERHEAD_TOKENS: int = 12


#: Content block overhead tokens. Mirrors
#: :data:`CONTENT_BLOCK_OVERHEAD_TOKENS` (``preemptive-compaction.ts:30``).
CONTENT_BLOCK_OVERHEAD_TOKENS: int = 6


#: Image block tokens. Mirrors
#: :data:`IMAGE_BLOCK_TOKENS` (``preemptive-compaction.ts:31``).
IMAGE_BLOCK_TOKENS: int = 2_000


#: Truncation route buffer tokens. Mirrors
#: :data:`TRUNCATION_ROUTE_BUFFER_TOKENS` (``preemptive-compaction.ts:32``).
TRUNCATION_ROUTE_BUFFER_TOKENS: int = 512


#: Min prompt budget ratio. Mirrors :data:`MIN_PROMPT_BUDGET_RATIO` from
#: ``agent-compaction-constants.ts``.
MIN_PROMPT_BUDGET_RATIO: float = 0.2


#: Min prompt budget tokens. Mirrors :data:`MIN_PROMPT_BUDGET_TOKENS` from
#: ``agent-compaction-constants.ts``.
MIN_PROMPT_BUDGET_TOKENS: int = 8_000


#: Safety margin. Mirrors :data:`SAFETY_MARGIN` from ``compaction.ts``.
SAFETY_MARGIN: int = 4_000


#: Branch summary prefix. Mirrors :data:`BRANCH_SUMMARY_PREFIX` from
#: ``runtime/index.ts``.
BRANCH_SUMMARY_PREFIX: str = "[branch summary]"


#: Branch summary suffix. Mirrors :data:`BRANCH_SUMMARY_SUFFIX` from
#: ``runtime/index.ts``.
BRANCH_SUMMARY_SUFFIX: str = "[/branch summary]"


#: Compaction summary prefix. Mirrors :data:`COMPACTION_SUMMARY_PREFIX` from
#: ``runtime/index.ts``.
COMPACTION_SUMMARY_PREFIX: str = "[compaction summary]"


#: Compaction summary suffix. Mirrors :data:`COMPACTION_SUMMARY_SUFFIX` from
#: ``runtime/index.ts``.
COMPACTION_SUMMARY_SUFFIX: str = "[/compaction summary]"


#: Preemptive-compaction decision shape. Mirrors
#: :class:`PreemptiveCompactionDecision`
#: (``preemptive-compaction.ts:35-44``).
PreemptiveCompactionDecision = Dict[str, Any]


#: LLM-boundary token pressure shape. Mirrors
#: :class:`LlmBoundaryTokenPressure` (``preemptive-compaction.ts:47-51``).
LlmBoundaryTokenPressure = Dict[str, Any]


#: Preemptive-compaction route type.
PreemptiveCompactionRoute = str


# ---------------------------------------------------------------------------
# Helpers (ported as-is)
# ---------------------------------------------------------------------------


def _estimate_string_chars(text: str) -> int:
    """Rough char count (CJK chars are typically 1 codepoint but 2 cells).

    Mirrors :func:`estimateStringChars` from ``utils/cjk-chars.ts``.
    For the focused-minimal port we treat each codepoint as one
    character; the CJK-aware logic is delegated to the
    ``estimateStringChars`` hook when present.
    """
    if not isinstance(text, str):
        return 0
    return len(text)


def estimate_string_token_pressure(
    text: str,
    chars_per_token: int = ESTIMATED_CHARS_PER_TOKEN,
) -> int:
    """Estimate token pressure for a string."""
    if not isinstance(text, str) or chars_per_token <= 0:
        return 0
    return int(math.ceil(_estimate_string_chars(text) / chars_per_token))


def estimate_json_payload_token_pressure(
    value: Any,
    chars_per_token: int = JSON_PAYLOAD_CHARS_PER_TOKEN,
) -> int:
    """Estimate token pressure for a JSON-serializable value."""
    if chars_per_token <= 0:
        return 0
    try:
        serialized = json.dumps(value)
    except Exception:
        return 256
    if not isinstance(serialized, str):
        return 1
    return int(math.ceil(_estimate_string_chars(serialized) / chars_per_token))


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for :func:`estimateStringChars` from ``utils/cjk-chars.ts``.
_ESTIMATE_STRING_CHARS: Callable[[str], int] = lambda _t: 0


def set_estimate_string_chars_hook(
    hook: Callable[[str], int],
) -> None:
    """Install a custom estimateStringChars hook."""
    global _ESTIMATE_STRING_CHARS
    _ESTIMATE_STRING_CHARS = hook


#: Hook for :func:`estimateToolResultReductionPotential` from
#: ``tool-result-truncation.ts``.
_ESTIMATE_TOOL_RESULT_REDUCTION_POTENTIAL: Callable[[Any], int] = (
    lambda _attempt: 0
)


def set_estimate_tool_result_reduction_potential_hook(
    hook: Callable[[Any], int],
) -> None:
    """Install a custom estimateToolResultReductionPotential hook."""
    global _ESTIMATE_TOOL_RESULT_REDUCTION_POTENTIAL
    _ESTIMATE_TOOL_RESULT_REDUCTION_POTENTIAL = hook


# ---------------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------------===


def estimate_llm_boundary_token_pressure(
    params: Dict[str, Any],
) -> LlmBoundaryTokenPressure:
    """Estimate token pressure for the LLM-boundary prompt.

    Mirrors :func:`estimateLlmBoundaryTokenPressure`
    (``preemptive-compaction.ts``).
    """
    messages = params.get("messages") or []
    if not isinstance(messages, list):
        messages = []
    estimated_prompt_tokens = MESSAGE_BOUNDARY_OVERHEAD_TOKENS * len(messages)
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            estimated_prompt_tokens += estimate_string_token_pressure(content)
        elif isinstance(content, list):
            estimated_prompt_tokens += CONTENT_BLOCK_OVERHEAD_TOKENS * len(content)
            for block in content:
                if not isinstance(block, dict):
                    continue
                kind = block.get("type") or block.get("kind")
                if kind in ("image",):
                    estimated_prompt_tokens += IMAGE_BLOCK_TOKENS
                elif "text" in block and isinstance(block["text"], str):
                    estimated_prompt_tokens += estimate_string_token_pressure(
                        block["text"]
                    )
                else:
                    estimated_prompt_tokens += estimate_json_payload_token_pressure(
                        block
                    )
        elif content is not None:
            estimated_prompt_tokens += estimate_json_payload_token_pressure(content)
    return {
        "estimatedPromptTokens": estimated_prompt_tokens,
        "source": "estimated",
    }


def estimate_rendered_llm_boundary_token_pressure(
    params: Dict[str, Any],
) -> LlmBoundaryTokenPressure:
    """Estimate token pressure for a rendered (post-conversion) prompt.

    Mirrors :func:`estimateRenderedLlmBoundaryTokenPressure`
    (``preemptive-compaction.ts``).
    """
    rendered = params.get("rendered") or ""
    if not isinstance(rendered, str):
        rendered = ""
    return {
        "estimatedPromptTokens": estimate_string_token_pressure(
            rendered, ESTIMATED_CHARS_PER_TOKEN
        ),
        "source": "rendered",
        "renderedChars": len(rendered),
    }


def should_preemptively_compact_before_prompt(
    params: Dict[str, Any],
) -> PreemptiveCompactionDecision:
    """Decide whether to preemptively compact before the next prompt.

    Mirrors :func:`shouldPreemptivelyCompactBeforePrompt`
    (``preemptive-compaction.ts``).
    """
    attempt = params.get("attempt") or {}
    prompt = params.get("prompt") or ""
    rendered = params.get("rendered") or ""
    context_window = int(params.get("contextWindow") or 0)
    reserve_tokens = int(params.get("reserveTokens") or SAFETY_MARGIN)

    boundary = (
        estimate_rendered_llm_boundary_token_pressure({"rendered": rendered})
        if rendered
        else estimate_llm_boundary_token_pressure({"messages": attempt.get("messages") or []})
    )
    estimated_prompt_tokens = int(boundary.get("estimatedPromptTokens") or 0)
    effective_reserve = max(reserve_tokens, MIN_PROMPT_BUDGET_TOKENS)
    prompt_budget = max(
        int(context_window * MIN_PROMPT_BUDGET_RATIO),
        MIN_PROMPT_BUDGET_TOKENS,
    )
    prompt_budget_before_reserve = max(0, prompt_budget - effective_reserve)
    tool_result_reducible_chars = _ESTIMATE_TOOL_RESULT_REDUCTION_POTENTIAL(attempt)
    overflow_tokens = max(
        0, estimated_prompt_tokens - prompt_budget_before_reserve
    )
    should_compact = overflow_tokens > 0
    route: PreemptiveCompactionRoute
    if not should_compact:
        route = "none"
    elif tool_result_reducible_chars > 0:
        route = "truncate-tool-results"
    else:
        route = "compact"
    return {
        "route": route,
        "shouldCompact": should_compact,
        "estimatedPromptTokens": estimated_prompt_tokens,
        "pressureSource": str(boundary.get("source") or "estimated"),
        "promptBudgetBeforeReserve": prompt_budget_before_reserve,
        "overflowTokens": overflow_tokens,
        "toolResultReducibleChars": tool_result_reducible_chars,
        "effectiveReserveTokens": effective_reserve,
    }


def format_pre_prompt_precheck_log(
    params: Dict[str, Any],
) -> str:
    """Format the pre-prompt precheck log line.

    Mirrors :func:`formatPrePromptPrecheckLog`
    (``preemptive-compaction.ts``).
    """
    decision = params.get("decision") or {}
    if not isinstance(decision, dict):
        decision = {}
    return (
        f"precheck route={decision.get('route', 'none')} "
        f"estimated={decision.get('estimatedPromptTokens', 0)} "
        f"overflow={decision.get('overflowTokens', 0)} "
        f"reducible={decision.get('toolResultReducibleChars', 0)}"
    )


def build_pre_prompt_context_budget_status(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the pre-prompt context-budget-status object.

    Mirrors :func:`buildPrePromptContextBudgetStatus`
    (``preemptive-compaction.ts``).
    """
    decision = params.get("decision") or {}
    if not isinstance(decision, dict):
        decision = {}
    return {
        "route": decision.get("route", "none"),
        "estimatedPromptTokens": int(decision.get("estimatedPromptTokens") or 0),
        "overflowTokens": int(decision.get("overflowTokens") or 0),
        "toolResultReducibleChars": int(
            decision.get("toolResultReducibleChars") or 0
        ),
        "effectiveReserveTokens": int(
            decision.get("effectiveReserveTokens") or 0
        ),
    }


__all__ = [
    "BRANCH_SUMMARY_PREFIX",
    "BRANCH_SUMMARY_SUFFIX",
    "COMPACTION_SUMMARY_PREFIX",
    "COMPACTION_SUMMARY_SUFFIX",
    "CONTENT_BLOCK_OVERHEAD_TOKENS",
    "ESTIMATED_CHARS_PER_TOKEN",
    "IMAGE_BLOCK_TOKENS",
    "JSON_PAYLOAD_CHARS_PER_TOKEN",
    "LlmBoundaryTokenPressure",
    "MESSAGE_BOUNDARY_OVERHEAD_TOKENS",
    "MIN_PROMPT_BUDGET_RATIO",
    "MIN_PROMPT_BUDGET_TOKENS",
    "PREEMPTIVE_OVERFLOW_ERROR_TEXT",
    "PreemptiveCompactionDecision",
    "PreemptiveCompactionRoute",
    "SAFETY_MARGIN",
    "TOOL_RESULT_CHARS_PER_TOKEN",
    "TRUNCATION_ROUTE_BUFFER_TOKENS",
    "build_pre_prompt_context_budget_status",
    "estimate_json_payload_token_pressure",
    "estimate_llm_boundary_token_pressure",
    "estimate_rendered_llm_boundary_token_pressure",
    "estimate_string_token_pressure",
    "format_pre_prompt_precheck_log",
    "set_estimate_string_chars_hook",
    "set_estimate_tool_result_reduction_potential_hook",
    "should_preemptively_compact_before_prompt",
]
