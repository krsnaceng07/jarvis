"""jarvis.agents.embedded_agent_runner.tool_result_truncation — bound tool-result char counts.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/tool-result-truncation.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`DEFAULT_MAX_LIVE_TOOL_RESULT_CHARS` — low-context default
  cap for a single live tool result text block.
- :func:`resolve_auto_live_tool_result_max_chars` — resolve the
  context-window-tiered max for a single live tool result.
- :func:`calculate_max_tool_result_chars_with_cap` — bound the
  per-result max by the context-window share.
- :func:`resolve_live_tool_result_max_chars` — the configured
  per-result cap, defaulting to the auto-resolved value.
- :func:`resolve_live_tool_result_aggregate_max_chars` — the
  aggregate budget across all live tool results.
- :func:`truncate_tool_result_message` — truncate one tool-result
  message's text content blocks to fit within ``max_chars``.
- :func:`truncate_oversized_tool_results_in_messages` —
  high-level helper: scan a list of messages and truncate any
  oversized tool results.
- :func:`session_likely_has_oversized_tool_results` — return
  True if any message in the list has a tool result over the
  per-result cap.

Phase 7.4b — focused minimal port.

The OpenClaw source is 1500+ lines and tightly coupled to the
session-manager, transcript file state, and runtime-transcript
target layers. The Python port keeps the public surface but
delegates the heavy session-manager-coupled helpers
(``truncateOversizedToolResultsInSessionManager``,
``truncateOversizedToolResultsInActiveTarget``,
``estimateToolResultReductionPotential``) to installable hooks
so the host can plug in the real session-manager layer as it
lands.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Union


#: Default max chars for a single live tool result. Mirrors
#: :data:`DEFAULT_MAX_LIVE_TOOL_RESULT_CHARS``
#: (``tool-result-truncation.ts:57``).
DEFAULT_MAX_LIVE_TOOL_RESULT_CHARS: int = 16_000

#: Max chars for a large-context (>= 100K tokens) live tool
#: result.
LARGE_CONTEXT_MAX_LIVE_TOOL_RESULT_CHARS: int = 32_000

#: Max chars for an XL-context (>= 200K tokens) live tool
#: result.
XL_CONTEXT_MAX_LIVE_TOOL_RESULT_CHARS: int = 64_000

#: Context-window threshold for the large-context tier.
LARGE_CONTEXT_TOOL_RESULT_TOKENS: int = 100_000

#: Context-window threshold for the XL-context tier.
XL_CONTEXT_TOOL_RESULT_TOKENS: int = 200_000

#: Multiplier used for the aggregate prompt tool-result cap.
PROMPT_TOOL_RESULT_AGGREGATE_CAP_MULTIPLIER: int = 4

#: Share of the context window reserved for tool-result history.
AGGREGATE_TOOL_RESULT_CONTEXT_SHARE: float = 0.5

#: Rough chars-per-token estimate.
_CHARS_PER_TOKEN: int = 4

#: Max share of the context window a single tool result may
#: consume.
MAX_TOOL_RESULT_CONTEXT_SHARE: float = 0.5

#: Minimum chars to keep when truncating.
MIN_KEEP_CHARS: int = 2_000

#: Recovery minimum (no chars).
RECOVERY_MIN_KEEP_CHARS: int = 0

#: Default suffix factory (the "truncated" notice).
DEFAULT_SUFFIX_FACTORY: Callable[[int], str] = (
    lambda truncated_chars: f"[... {max(1, int(truncated_chars))} chars truncated]"
)

#: Compact-recovery suffix factory.
COMPACT_RECOVERY_SUFFIX_FACTORY: Callable[[int], str] = (
    lambda truncated_chars: (
        f"[... {max(1, int(truncated_chars))} chars truncated; narrow args]"
    )
)

#: Aggregate elision marker.
AGGREGATE_ELISION_MARKER: str = (
    "[tool result elided: aggregate tool-result budget exceeded; "
    "rerun the command if the output is needed]"
)


def set_default_suffix_factory(
    factory: Callable[[int], str],
) -> None:
    """Install a custom default suffix factory."""
    global DEFAULT_SUFFIX_FACTORY
    DEFAULT_SUFFIX_FACTORY = factory


def resolve_auto_live_tool_result_max_chars(
    context_window_tokens: float,
) -> int:
    """Resolve the context-window-tiered max for a single live tool result.

    Mirrors :func:`resolveAutoLiveToolResultMaxChars``
    (``tool-result-truncation.ts:291-303``).
    """
    import math

    if not math.isfinite(context_window_tokens):
        return DEFAULT_MAX_LIVE_TOOL_RESULT_CHARS
    tokens = int(math.floor(context_window_tokens))
    if tokens >= XL_CONTEXT_TOOL_RESULT_TOKENS:
        return XL_CONTEXT_MAX_LIVE_TOOL_RESULT_CHARS
    if tokens >= LARGE_CONTEXT_TOOL_RESULT_TOKENS:
        return LARGE_CONTEXT_MAX_LIVE_TOOL_RESULT_CHARS
    return DEFAULT_MAX_LIVE_TOOL_RESULT_CHARS


def calculate_max_tool_result_chars_with_cap(
    context_window_tokens: float,
    hard_cap_chars: float,
) -> int:
    """Bound the per-result max by the context-window share.

    Mirrors :func:`calculateMaxToolResultCharsWithCap``
    (``tool-result-truncation.ts:305-313``).
    """
    import math

    max_tokens = math.floor(context_window_tokens * MAX_TOOL_RESULT_CONTEXT_SHARE)
    max_chars = max_tokens * _CHARS_PER_TOKEN
    return min(max_chars, max(1, int(hard_cap_chars)))


def resolve_live_tool_result_max_chars(
    params: Dict[str, Any],
) -> int:
    """Resolve the configured per-result cap.

    Mirrors :func:`resolveLiveToolResultMaxChars``
    (``tool-result-truncation.ts:315-323``).
    """
    context_window_tokens = params.get("contextWindowTokens", 0)
    configured_cap = _resolve_configured_tool_result_max_chars(
        params.get("cfg"), params.get("agentId")
    )
    cap = (
        configured_cap
        if configured_cap is not None
        else resolve_auto_live_tool_result_max_chars(context_window_tokens)
    )
    return calculate_max_tool_result_chars_with_cap(context_window_tokens, cap)


def resolve_live_tool_result_aggregate_max_chars(
    params: Dict[str, Any],
) -> int:
    """Resolve the aggregate budget across all live tool results.

    Mirrors :func:`resolveLiveToolResultAggregateMaxChars``
    (``tool-result-truncation.ts:325-355``).
    """
    import math

    per_result_max = max(
        1,
        int(
            math.floor(
                params.get("perResultMaxChars")
                or resolve_live_tool_result_max_chars(
                    {
                        "contextWindowTokens": params.get("contextWindowTokens", 0),
                        "cfg": params.get("cfg"),
                        "agentId": params.get("agentId"),
                    }
                )
            )
        ),
    )
    context_window_tokens = (
        max(1, int(math.floor(params.get("contextWindowTokens", 0))))
        if math.isfinite(params.get("contextWindowTokens", 0))
        else 1
    )
    context_share_chars = int(
        math.floor(context_window_tokens * _CHARS_PER_TOKEN * AGGREGATE_TOOL_RESULT_CONTEXT_SHARE)
    )
    return max(
        per_result_max * PROMPT_TOOL_RESULT_AGGREGATE_CAP_MULTIPLIER,
        context_share_chars,
    )


#: Configured tool-result max chars resolver. The host installs
#: the real :func:`resolveAgentContextLimits`` when the
#: agent-context-limits layer lands. The default returns ``None``.
_RESOLVE_CONFIGURED_TOOL_RESULT_MAX_CHARS: Callable[..., Optional[int]] = (
    lambda _cfg, _agent_id: None
)


def set_resolve_configured_tool_result_max_chars_hook(
    hook: Callable[..., Optional[int]],
) -> None:
    """Install a custom configured-tool-result-max-chars hook."""
    global _RESOLVE_CONFIGURED_TOOL_RESULT_MAX_CHARS
    _RESOLVE_CONFIGURED_TOOL_RESULT_MAX_CHARS = hook


def _resolve_configured_tool_result_max_chars(
    cfg: Any,
    agent_id: Optional[str],
) -> Optional[int]:
    return _RESOLVE_CONFIGURED_TOOL_RESULT_MAX_CHARS(cfg, agent_id)


def _is_tool_result_text_block(
    block: Any,
) -> bool:
    """Return True if the block is a tool-result text block.

    Mirrors :func:`isToolResultTextBlock``
    (``tool-result-truncation.ts:439-450``).
    """
    if not block or not isinstance(block, dict):
        return False
    type_ = block.get("type")
    if type_ != "text" and type_ != "toolResult":
        return False
    return isinstance(block.get("text"), str)


def _get_tool_result_text_length(msg: Any) -> int:
    """Sum the text content of a tool-result message.

    Mirrors :func:`getToolResultTextLength``
    (``tool-result-truncation.ts:360-378``).
    """
    if not msg or not isinstance(msg, dict):
        return 0
    if msg.get("role") != "toolResult":
        return 0
    content = msg.get("content")
    if not isinstance(content, list):
        return 0
    total = 0
    for block in content:
        if _is_tool_result_text_block(block):
            text = block.get("text", "")
            if isinstance(text, str):
                total += len(text)
    return total


def _resolve_suffix_factory(
    suffix: Union[None, str, Callable[[int], str]],
) -> Callable[[int], str]:
    """Resolve the suffix factory from the user-supplied option.

    Mirrors :func:`resolveSuffixFactory``
    (``tool-result-truncation.ts:139-149``).
    """
    if callable(suffix):
        return suffix
    if isinstance(suffix, str):
        return lambda _truncated: suffix
    return DEFAULT_SUFFIX_FACTORY


def _resolve_effective_min_keep_chars(
    *,
    max_chars: int,
    min_keep_chars: int,
    suffix_factory: Callable[[int], str],
) -> int:
    """Resolve the effective min-keep chars.

    Mirrors :func:`resolveEffectiveMinKeepChars``
    (``tool-result-truncation.ts:180-...``).
    """
    return min(min_keep_chars, max_chars)


def _truncate_tool_result_text(
    text: str,
    block_budget: int,
    *,
    suffix: Callable[[int], str],
    min_keep_chars: int,
) -> str:
    """Truncate ``text`` to ``block_budget`` characters.

    Mirrors :func:`truncateToolResultText``
    (``tool-result-truncation.ts:~250-...``).
    """
    if len(text) <= block_budget:
        return text
    available = max(1, block_budget - max(0, min_keep_chars))
    truncated_chars = len(text) - available
    if truncated_chars <= 0:
        return text[:block_budget]
    suffix_text = suffix(truncated_chars)
    keep = max(min_keep_chars, block_budget - len(suffix_text))
    if keep <= 0:
        return suffix_text[:block_budget]
    return text[:keep] + suffix_text


def truncate_tool_result_message(
    msg: Any,
    max_chars: int,
    options: Optional[Dict[str, Any]] = None,
) -> Any:
    """Truncate a tool-result message's text content blocks.

    Mirrors :func:`truncateToolResultMessage``
    (``tool-result-truncation.ts:384-437``).
    """
    options = options or {}
    suffix_factory = _resolve_suffix_factory(options.get("suffix"))
    min_keep = _resolve_effective_min_keep_chars(
        max_chars=max_chars,
        min_keep_chars=options.get("minKeepChars", MIN_KEEP_CHARS),
        suffix_factory=suffix_factory,
    )
    if not msg or not isinstance(msg, dict):
        return msg
    content = msg.get("content")
    if not isinstance(content, list):
        return msg
    total_text = _get_tool_result_text_length(msg)
    if total_text <= max_chars:
        return msg
    new_content: List[Any] = []
    for block in content:
        if not _is_tool_result_text_block(block):
            new_content.append(block)
            continue
        text = block.get("text", "")
        if not isinstance(text, str):
            new_content.append(block)
            continue
        block_share = len(text) / total_text if total_text else 0
        proportional = int(max_chars * block_share)
        default_suffix = suffix_factory(max(1, len(text) - proportional))
        block_budget = max(
            1,
            min(
                max_chars,
                max(min_keep + len(default_suffix), proportional),
            ),
        )
        truncated = _truncate_tool_result_text(
            text,
            block_budget,
            suffix=suffix_factory,
            min_keep_chars=min_keep,
        )
        next_block = dict(block)
        next_block["text"] = truncated
        if isinstance(block.get("content"), str):
            next_block["content"] = truncated
        new_content.append(next_block)
    return {**msg, "content": new_content}


def truncate_oversized_tool_results_in_messages(
    messages: List[Any],
    max_chars: int,
) -> List[Any]:
    """Truncate any oversized tool results in a list of messages.

    Mirrors :func:`truncateOversizedToolResultsInMessages``
    (``tool-result-truncation.ts:569-...``).
    """
    out: List[Any] = []
    for msg in messages:
        if not isinstance(msg, dict):
            out.append(msg)
            continue
        if msg.get("role") != "toolResult":
            out.append(msg)
            continue
        if _get_tool_result_text_length(msg) <= max_chars:
            out.append(msg)
            continue
        out.append(truncate_tool_result_message(msg, max_chars))
    return out


def session_likely_has_oversized_tool_results(
    messages: List[Any],
    per_result_max_chars: int,
) -> bool:
    """Return True if any message has a tool result over the cap.

    Mirrors :func:`sessionLikelyHasOversizedToolResults``
    (``tool-result-truncation.ts:1556-...``).
    """
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "toolResult":
            continue
        if _get_tool_result_text_length(msg) > per_result_max_chars:
            return True
    return False


__all__ = [
    "AGGREGATE_ELISION_MARKER",
    "COMPACT_RECOVERY_SUFFIX_FACTORY",
    "DEFAULT_MAX_LIVE_TOOL_RESULT_CHARS",
    "DEFAULT_SUFFIX_FACTORY",
    "MIN_KEEP_CHARS",
    "PROMPT_TOOL_RESULT_AGGREGATE_CAP_MULTIPLIER",
    "calculate_max_tool_result_chars_with_cap",
    "resolve_auto_live_tool_result_max_chars",
    "resolve_live_tool_result_aggregate_max_chars",
    "resolve_live_tool_result_max_chars",
    "session_likely_has_oversized_tool_results",
    "set_default_suffix_factory",
    "set_resolve_configured_tool_result_max_chars_hook",
    "truncate_oversized_tool_results_in_messages",
    "truncate_tool_result_message",
]
