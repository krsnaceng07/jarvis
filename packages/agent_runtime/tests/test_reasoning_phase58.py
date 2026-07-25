"""Phase 5.8 gate: ``reasoning.py`` — the three meanings of "off".

Ported from ``packages/agent-core/src/reasoning.ts``, which has no test
file in OpenClaw. These vectors exist because the function returns three
different things for the same input level and the difference is invisible
at runtime:

``None``
    omit the field, provider default applies
``"off"``
    explicitly disable, needed for models that reason by default
``"low"``
    substitute the lowest level, for models that cannot disable reasoning

Returning ``None`` where ``"off"`` belonged leaves reasoning switched on
after the user turned it off, and the request still succeeds. That is the
failure this suite is here to catch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from jarvis_agent.reasoning import (
    ENABLED_THINKING_LEVELS,
    is_enabled_thinking_level,
    resolve_agent_reasoning_option,
)


@dataclass
class FakeModel:
    """Structural stand-in for ``Model``.

    Only the three attributes ``resolve_agent_reasoning_option`` reads are
    present: ``id``, ``api``, ``thinking_level_map`` (plus ``params``, which
    the identity predicates consult).
    """

    id: str = ""
    api: str = "anthropic-messages"
    thinking_level_map: dict[str, str | None] | None = None
    params: dict[str, Any] | None = field(default=None)


# ── non-off levels pass straight through ─────────────────────────────


@pytest.mark.parametrize("level", ["minimal", "low", "medium", "high", "xhigh", "max"])
def test_non_off_levels_pass_through_unchanged(level: str) -> None:
    """Translation to a token budget or vendor string is the adapter's job.

    If this function mapped levels itself, the mapping would exist in two
    places and drift.
    """
    model = FakeModel(id="claude-fable-5")
    assert resolve_agent_reasoning_option(model, level) == level  # type: ignore[arg-type]


def test_non_off_level_ignores_the_model_entirely() -> None:
    """A non-off level is returned even for a model with no reasoning support."""
    assert resolve_agent_reasoning_option(FakeModel(id="gemini-3-pro", api="google"), "high") == (
        "high"
    )


# ── the "off" branch ─────────────────────────────────────────────────


def test_off_on_an_unrelated_model_sends_nothing() -> None:
    """The common case: omit the field and let the provider default apply."""
    model = FakeModel(id="gemini-3-pro", api="google-generative-ai")
    assert resolve_agent_reasoning_option(model, "off") is None


def test_off_map_entry_wins_over_every_family_rule() -> None:
    """An explicit provider-published ``off`` mapping is authoritative.

    Fable 5 would otherwise get the ``"low"`` substitution; a published map
    must override it, because the map came from the route's own contract.
    """
    model = FakeModel(id="claude-fable-5", thinking_level_map={"off": "medium"})
    assert resolve_agent_reasoning_option(model, "off") == "medium"


def test_off_map_entry_must_be_an_enabled_level_to_be_used() -> None:
    """``isEnabledThinkingLevel`` guards provider-supplied data.

    A map claiming ``off -> "off"`` is not an enabled level, so it falls
    through to the family rules rather than being echoed back blindly.
    """
    model = FakeModel(id="claude-sonnet-5", thinking_level_map={"off": "off"})
    # Falls through to the Sonnet 5 rule, which also yields "off" — but by
    # the family path, not by trusting the map value.
    assert resolve_agent_reasoning_option(model, "off") == "off"

    unrelated = FakeModel(id="gemini-3-pro", api="google", thinking_level_map={"off": "bogus"})
    assert resolve_agent_reasoning_option(unrelated, "off") is None


def test_off_map_entry_of_none_means_unsupported_and_falls_through() -> None:
    """``??`` treats null as absent.

    A ``None`` value marks the level unsupported, which is not the same as
    a usable mapping, so the Fable 5 substitution still applies.
    """
    model = FakeModel(id="claude-fable-5", thinking_level_map={"off": None})
    assert resolve_agent_reasoning_option(model, "off") == "low"


@pytest.mark.parametrize("api", ["anthropic-messages", "bedrock-converse-stream"])
def test_fable5_cannot_disable_reasoning_so_off_becomes_low(api: str) -> None:
    """Fable 5 substitutes the lowest level on both Anthropic-style APIs.

    Bedrock is included because it reaches the same model through a
    different api id; omitting it would send a disable request that the
    model rejects.
    """
    model = FakeModel(id="claude-fable-5", api=api)
    assert resolve_agent_reasoning_option(model, "off") == "low"


def test_fable5_on_a_non_anthropic_api_does_not_substitute() -> None:
    """The api check is a real guard, not decoration.

    A Fable 5 id reached through an OpenAI-compatible gateway takes the
    generic path — the gateway, not this function, owns that translation.
    """
    model = FakeModel(id="claude-fable-5", api="openai-completions")
    assert resolve_agent_reasoning_option(model, "off") is None


def test_sonnet5_reasons_by_default_so_off_must_be_explicit() -> None:
    """Returning ``None`` here would leave reasoning on."""
    model = FakeModel(id="claude-sonnet-5", api="anthropic-messages")
    assert resolve_agent_reasoning_option(model, "off") == "off"


def test_sonnet5_rule_does_not_extend_to_bedrock() -> None:
    """Deliberate asymmetry with the Fable 5 branch, preserved from the TS.

    ``reasoning.ts`` checks both APIs for Fable 5 but only
    ``anthropic-messages`` for Sonnet 5. This asserts the asymmetry so a
    future "cleanup" that unifies the two checks fails here instead of
    changing provider behaviour silently.
    """
    model = FakeModel(id="claude-sonnet-5", api="bedrock-converse-stream")
    assert resolve_agent_reasoning_option(model, "off") is None


def test_fable5_takes_precedence_over_the_sonnet_branch() -> None:
    """Order matters: the low-substitution is checked before explicit off."""
    model = FakeModel(id="claude-fable-5", api="anthropic-messages")
    result = resolve_agent_reasoning_option(model, "off")
    assert result == "low"
    assert result != "off"


def test_identity_normalization_reaches_this_function() -> None:
    """A dotted/prefixed deployment id still matches the family rule.

    Without normalization this returns ``None`` and reasoning stays on for
    a real production model id.
    """
    model = FakeModel(id="anthropic/claude-sonnet-5-20991231", api="anthropic-messages")
    assert resolve_agent_reasoning_option(model, "off") == "off"

    aliased = FakeModel(
        id="internal-fast-route",
        api="anthropic-messages",
        params={"canonicalModelId": "claude-fable-5"},
    )
    assert resolve_agent_reasoning_option(aliased, "off") == "low"


def test_boundary_ids_do_not_trigger_family_rules() -> None:
    """``claude-sonnet-50`` is a different model from ``claude-sonnet-5``."""
    assert resolve_agent_reasoning_option(FakeModel(id="claude-sonnet-50"), "off") is None
    assert resolve_agent_reasoning_option(FakeModel(id="claude-fable-50"), "off") is None


# ── the level predicate ──────────────────────────────────────────────


def test_enabled_levels_exclude_off() -> None:
    """Parity: ``Exclude<..., "off">``. The set must not contain ``off``."""
    assert ENABLED_THINKING_LEVELS == frozenset(
        {"minimal", "low", "medium", "high", "xhigh", "max"}
    )
    assert "off" not in ENABLED_THINKING_LEVELS


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("low", True),
        ("max", True),
        ("off", False),
        (None, False),
        ("", False),
        ("bogus", False),
        (0, False),
    ],
)
def test_is_enabled_thinking_level_tolerates_provider_junk(value: Any, expected: bool) -> None:
    """The value comes from provider-supplied data, so it may be anything."""
    assert is_enabled_thinking_level(value) is expected


def test_missing_thinking_level_map_is_tolerated() -> None:
    assert resolve_agent_reasoning_option(FakeModel(id="claude-fable-5"), "off") == "low"
