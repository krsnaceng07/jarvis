"""jarvis_agent.reasoning — map an agent thinking level to a provider option.

OpenClaw parity: ``packages/agent-core/src/reasoning.ts``.

This is 43 lines of TypeScript that decide one thing: what to put in
``SimpleStreamOptions.reasoning`` for a turn. The subtlety is entirely in
what ``"off"`` means, and there are three different answers:

``None``
    Send nothing. The provider uses its own default. This is the plain
    non-reasoning case.
``"off"``
    Send an explicit disable. Needed for models that reason *by default* —
    omitting the field would leave reasoning on when the user asked for it
    off.
a level such as ``"low"``
    Some models cannot actually turn reasoning off. Asking them to do so is
    an error, so the lowest available level substitutes for "off".

Returning ``None`` where ``"off"`` was required (or the reverse) is a
silent failure: the request succeeds and the user simply gets the wrong
behaviour, plus the token bill that goes with it.
"""

from __future__ import annotations

from typing import Any

from jarvis_llm.model_contracts import (
    resolve_claude_fable5_model_identity,
    resolve_claude_sonnet5_model_identity,
)
from jarvis_llm.types import Model

from .types import ThinkingLevel

#: Levels that mean "reasoning is on". Parity: ``ENABLED_THINKING_LEVELS``,
#: which the TS derives as ``Exclude<..., "off">`` from the provider option
#: type. Python has no ``Exclude``, so the set is written out — and
#: :func:`is_enabled_thinking_level` guards it at runtime the same way the
#: TS type predicate does.
ENABLED_THINKING_LEVELS: frozenset[str] = frozenset(
    {"minimal", "low", "medium", "high", "xhigh", "max"}
)

#: APIs whose Claude routes need the "off means low" fallback. Parity: the
#: inline ``model.api === ... || model.api === ...`` check. Bedrock is
#: included because the same model is reached through a different API id.
_ANTHROPIC_STYLE_APIS: frozenset[str] = frozenset(
    {"anthropic-messages", "bedrock-converse-stream"}
)


def is_enabled_thinking_level(value: Any) -> bool:
    """Parity: ``isEnabledThinkingLevel``, the TS type predicate.

    Deliberately accepts ``Any``: the value being tested comes out of
    ``thinking_level_map``, which is provider-supplied data and may hold
    ``None`` or an unrecognized string. Narrowing the parameter type would
    move the problem to the call site without removing it.
    """
    return value in ENABLED_THINKING_LEVELS


def resolve_agent_reasoning_option(
    model: Model,
    thinking_level: ThinkingLevel,
) -> str | None:
    """Resolve ``SimpleStreamOptions.reasoning`` for one turn.

    Parity: ``resolveAgentReasoningOption``.

    Any level other than ``"off"`` passes straight through — the provider
    adapter is what translates a normalized level into a token budget or a
    vendor effort string, not this function.

    For ``"off"`` the order is: an explicit ``off`` entry in the model's
    ``thinking_level_map`` wins; failing that, Claude Fable 5 on an
    Anthropic-style API substitutes ``"low"`` because it cannot disable
    reasoning; failing that, Claude Sonnet 5 on ``anthropic-messages`` gets
    an explicit ``"off"`` because it reasons by default; otherwise nothing
    is sent.
    """
    if thinking_level != "off":
        return thinking_level

    off_fallback: Any = None
    level_map = model.thinking_level_map
    if level_map is not None and "off" in level_map:
        off_fallback = level_map["off"]

    if off_fallback is None:
        # ``??`` in the TS: only reached when the map had no usable ``off``
        # entry. Note a map entry of ``None`` (level unsupported) also lands
        # here, which matches ``?? `` treating null as absent.
        if model.api in _ANTHROPIC_STYLE_APIS and (
            resolve_claude_fable5_model_identity(model) is not None
        ):
            off_fallback = "low"

    if is_enabled_thinking_level(off_fallback):
        return off_fallback

    # Sonnet 5 reasons by default, so "off" must be stated, not omitted.
    # Only on the direct Anthropic API — the TS does not extend this to
    # Bedrock here, unlike the Fable 5 branch above, and that asymmetry is
    # preserved rather than "fixed".
    if model.api == "anthropic-messages" and (
        resolve_claude_sonnet5_model_identity(model) is not None
    ):
        return "off"
    return None


__all__ = [
    "ENABLED_THINKING_LEVELS",
    "is_enabled_thinking_level",
    "resolve_agent_reasoning_option",
]
