"""Phase 5.8 gate: ``model_contracts.py`` identity and capability predicates.

Ported from ``packages/llm-core/src/model-contracts/anthropic.ts``. That
file ships no test of its own in OpenClaw, so these vectors are derived
from the regexes it encodes — specifically the three things a
transliterated port gets wrong:

1. The word-boundary lookahead. ``claude-sonnet-55`` must **not** match
   ``claude-sonnet-5``. A ``startswith``/``in`` port matches it.
2. The separator normalization. ``claude_fable_5`` and ``Claude.Fable.5``
   are the same model.
3. ``canonicalModelId`` in ``params`` outranks ``id``.

The cost of getting these wrong is not a crash: it is sending an
unsupported ``xhigh`` effort or a manual token budget to a model that
rejects it, or silently disabling reasoning on a model that supports it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from jarvis_llm.model_contracts import (
    CLAUDE_FABLE_5_THINKING_PROFILE,
    CLAUDE_SONNET_5_THINKING_PROFILE,
    requires_claude_default_sampling,
    requires_claude_mandatory_adaptive_thinking,
    resolve_claude_fable5_model_identity,
    resolve_claude_model_identity,
    resolve_claude_mythos5_model_identity,
    resolve_claude_native_thinking_level_map,
    resolve_claude_sonnet5_model_identity,
    supports_claude_adaptive_thinking,
    supports_claude_native_max_effort,
    supports_claude_native_xhigh_effort,
)


@dataclass
class Ref:
    """Minimal structural stand-in for ``Model``. Parity: ``ClaudeModelRef``."""

    id: str = ""
    params: dict[str, Any] | None = None
    thinking_level_map: dict[str, str | None] | None = field(default=None)


# ── normalization ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("claude-fable-5", "claude-fable-5"),
        ("anthropic/claude-fable-5", "claude-fable-5"),
        # Dots, underscores and whitespace all collapse to a hyphen.
        ("claude_fable_5", "claude-fable-5"),
        ("claude.fable.5", "claude-fable-5"),
        ("Claude-Fable-5", "claude-fable-5"),
        ("  claude-fable-5  ", "claude-fable-5"),
        # Bedrock/Vertex-style deployment ids: everything before the anchor
        # is dropped, including the separator itself.
        ("us.anthropic.claude-fable-5-v1:0", "claude-fable-5-v1:0"),
        ("bedrock/claude-sonnet-5", "claude-sonnet-5"),
        # No "claude-" anchor at all: normalized id returned untouched.
        ("gemini-3-pro", "gemini-3-pro"),
        ("", ""),
    ],
)
def test_resolve_identity_normalizes_deployment_ids(model_id: str, expected: str) -> None:
    assert resolve_claude_model_identity(Ref(id=model_id)) == expected


def test_canonical_model_id_param_outranks_the_id() -> None:
    """A gateway alias must not hide the real model behind it.

    If ``id`` won, an alias like ``my-fast-model`` would resolve to no
    Claude family and every capability predicate would return False —
    silently downgrading a Fable 5 route.
    """
    ref = Ref(id="my-gateway-alias", params={"canonicalModelId": "claude-fable-5"})
    assert resolve_claude_model_identity(ref) == "claude-fable-5"
    assert resolve_claude_fable5_model_identity(ref) == "claude-fable-5"


def test_non_string_canonical_model_id_is_ignored() -> None:
    """``typeof ... === "string"`` guard: a numeric value falls back to id."""
    ref = Ref(id="claude-sonnet-5", params={"canonicalModelId": 42})
    assert resolve_claude_model_identity(ref) == "claude-sonnet-5"


def test_missing_params_is_tolerated() -> None:
    assert resolve_claude_model_identity(Ref(id="claude-sonnet-5", params=None)) == (
        "claude-sonnet-5"
    )


# ── family resolution ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("claude-fable-5", "claude-fable-5"),
        # The returned suffix keeps the version qualifier, so callers can
        # distinguish dated snapshots. Truthiness alone is not the contract.
        ("claude-fable-5-20991231", "claude-fable-5-20991231"),
        ("anthropic/claude-fable-5-v1:0", "claude-fable-5-v1:0"),
        ("claude-sonnet-5", None),
        # Boundary: a longer number must not match. This is the case a
        # substring check gets wrong.
        ("claude-fable-50", None),
        ("claude-fable-55", None),
        ("", None),
    ],
)
def test_fable5_identity_respects_the_word_boundary(model_id: str, expected: str | None) -> None:
    assert resolve_claude_fable5_model_identity(Ref(id=model_id)) == expected


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("claude-sonnet-5", "claude-sonnet-5"),
        ("claude-sonnet-5-20991231", "claude-sonnet-5-20991231"),
        ("claude-sonnet-50", None),
        ("claude-sonnet-4-6", None),
        ("claude-fable-5", None),
    ],
)
def test_sonnet5_identity_respects_the_word_boundary(model_id: str, expected: str | None) -> None:
    assert resolve_claude_sonnet5_model_identity(Ref(id=model_id)) == expected


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("claude-mythos-5", "claude-mythos-5"),
        ("claude-mythos-preview", None),
        ("claude-mythos-50", None),
    ],
)
def test_mythos5_identity_respects_the_word_boundary(model_id: str, expected: str | None) -> None:
    assert resolve_claude_mythos5_model_identity(Ref(id=model_id)) == expected


# ── capability predicates ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("claude-fable-5", True),
        ("claude-mythos-5", True),
        ("claude-mythos-preview", True),
        # Adaptive-capable but not *mandatory*: these accept manual budgets.
        ("claude-sonnet-5", False),
        ("claude-opus-4-6", False),
        ("gemini-3-pro", False),
    ],
)
def test_mandatory_adaptive_thinking(model_id: str, expected: bool) -> None:
    assert requires_claude_mandatory_adaptive_thinking(Ref(id=model_id)) is expected


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("claude-fable-5", True),
        ("claude-mythos-5", True),
        ("claude-mythos-preview", True),
        ("claude-opus-4-6", True),
        ("claude-opus-4-7", True),
        ("claude-opus-4-8", True),
        ("claude-sonnet-5", True),
        ("claude-sonnet-4-6", True),
        ("claude-opus-4-5", False),
        ("claude-sonnet-4-5", False),
        ("gemini-3-pro", False),
    ],
)
def test_supports_adaptive_thinking(model_id: str, expected: bool) -> None:
    assert supports_claude_adaptive_thinking(Ref(id=model_id)) is expected


def test_max_and_xhigh_families_differ() -> None:
    """The load-bearing asymmetry: opus-4-6 has max effort but not xhigh.

    The two regexes look nearly identical and are one edit away from being
    merged. If they were merged, opus-4-6 would be sent ``xhigh``, which it
    does not support.
    """
    opus46 = Ref(id="claude-opus-4-6")
    assert supports_claude_native_max_effort(opus46) is True
    assert supports_claude_native_xhigh_effort(opus46) is False

    sonnet46 = Ref(id="claude-sonnet-4-6")
    assert supports_claude_native_max_effort(sonnet46) is True
    assert supports_claude_native_xhigh_effort(sonnet46) is False

    for model_id in ("claude-fable-5", "claude-mythos-5", "claude-opus-4-7", "claude-sonnet-5"):
        ref = Ref(id=model_id)
        assert supports_claude_native_max_effort(ref) is True, model_id
        assert supports_claude_native_xhigh_effort(ref) is True, model_id


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("claude-fable-5", True),
        ("claude-mythos-preview", True),
        ("claude-sonnet-5", True),
        # xhigh-incapable, so caller sampling params are allowed.
        ("claude-opus-4-6", False),
        ("gemini-3-pro", False),
    ],
)
def test_requires_default_sampling(model_id: str, expected: bool) -> None:
    assert requires_claude_default_sampling(Ref(id=model_id)) is expected


# ── native thinking-level map ────────────────────────────────────────


def test_published_map_always_wins() -> None:
    published: dict[str, str | None] = {"max": "custom-max"}
    ref = Ref(id="claude-fable-5", thinking_level_map=published)
    assert resolve_claude_native_thinking_level_map(ref) is published


def test_published_empty_map_is_not_overwritten() -> None:
    """``!== undefined``, not truthiness.

    An explicitly published ``{}`` means "no native level mapping". A port
    using ``if ref.thinking_level_map:`` would replace it with defaults and
    start sending native effort values the route never advertised.
    """
    empty: dict[str, str | None] = {}
    ref = Ref(id="claude-fable-5", thinking_level_map=empty)
    assert resolve_claude_native_thinking_level_map(ref) is empty


def test_fills_native_map_for_xhigh_capable_models() -> None:
    result = resolve_claude_native_thinking_level_map(Ref(id="claude-fable-5"))
    assert result == {"xhigh": "xhigh", "max": "max"}


def test_marks_xhigh_unsupported_rather_than_omitting_it() -> None:
    """``None`` means unsupported; absent means "use provider default".

    opus-4-6 gets ``xhigh: None`` — an explicit "do not offer this level".
    Omitting the key instead would let a caller's ``xhigh`` fall through to
    the provider default and quietly succeed at the wrong effort.
    """
    result = resolve_claude_native_thinking_level_map(Ref(id="claude-opus-4-6"))
    assert result == {"xhigh": None, "max": "max"}
    assert result is not None
    assert "xhigh" in result


def test_returns_none_for_models_without_native_max_effort() -> None:
    assert resolve_claude_native_thinking_level_map(Ref(id="claude-opus-4-5")) is None
    assert resolve_claude_native_thinking_level_map(Ref(id="gemini-3-pro")) is None


# ── thinking profiles ────────────────────────────────────────────────


def test_thinking_profiles_match_openclaw() -> None:
    """Level lists are identical; only Fable 5 carries the preserve flag."""
    expected_levels = [
        {"id": level}
        for level in ("off", "minimal", "low", "medium", "high", "xhigh", "adaptive", "max")
    ]
    assert CLAUDE_FABLE_5_THINKING_PROFILE["levels"] == expected_levels
    assert CLAUDE_SONNET_5_THINKING_PROFILE["levels"] == expected_levels
    assert CLAUDE_FABLE_5_THINKING_PROFILE["defaultLevel"] == "high"
    assert CLAUDE_SONNET_5_THINKING_PROFILE["defaultLevel"] == "high"
    assert CLAUDE_FABLE_5_THINKING_PROFILE["preserveWhenCatalogReasoningFalse"] is True
    assert "preserveWhenCatalogReasoningFalse" not in CLAUDE_SONNET_5_THINKING_PROFILE
