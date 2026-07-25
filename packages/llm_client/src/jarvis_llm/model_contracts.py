"""jarvis_llm.model_contracts — Claude model-identity predicates.

OpenClaw parity: ``packages/llm-core/src/model-contracts/anthropic.ts``.

Why this file exists here and not in the agent package
=====================================================
``agent-core/src/reasoning.ts`` imports ``resolveClaudeFable5ModelIdentity``
and ``resolveClaudeSonnet5ModelIdentity`` *from llm-core*. The predicates
describe what a model supports, which is a provider contract, not agent
policy — so the port keeps the same boundary. Inlining a guess in the agent
package would silently change which models get reasoning enabled.

What "identity" means
=====================
These are not equality checks against a model id. A single logical model
arrives under many spellings: ``claude-fable-5``, ``anthropic/claude-fable-5``,
a Bedrock ARN suffix, a Vertex deployment name, an id with dots or
underscores instead of hyphens. ``resolve_claude_model_identity`` normalizes
all of those to one canonical form, and each ``resolve_*_identity`` function
returns the matched-and-onward slice (a truthy string) or ``None``.

The returned *string* matters, not just its truthiness: the suffix carries
the version/date qualifier, so callers that need to distinguish
``claude-fable-5`` from ``claude-fable-5-20991231`` can.
"""

from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable

# ─────────────────────────────────────────────────────────────────────
# Model reference shape
# ─────────────────────────────────────────────────────────────────────


@runtime_checkable
class ClaudeModelRef(Protocol):
    """Structural shape these predicates need. Parity: ``ClaudeModelRef``.

    TypeScript accepts any object with optional ``id`` and ``params``;
    :class:`jarvis_llm.types.Model` satisfies this, and so does any test
    double. A Protocol keeps that structural typing rather than forcing
    callers to construct a full ``Model``.
    """

    id: str
    params: dict[str, Any] | None


@runtime_checkable
class ClaudeEffortModelRef(ClaudeModelRef, Protocol):
    """Parity: ``ClaudeEffortModelRef`` — adds the thinking-level map."""

    thinking_level_map: dict[str, str | None] | None


# ─────────────────────────────────────────────────────────────────────
# Thinking profiles
# ─────────────────────────────────────────────────────────────────────

#: Parity: ``CLAUDE_FABLE_5_THINKING_PROFILE``.
#:
#: ``preserve_when_catalog_reasoning_false`` is the field that is easy to
#: drop and expensive to lose: some catalogs publish ``reasoning: false``
#: for this model even though it reasons, and this flag tells the router to
#: keep the profile anyway instead of stripping thinking support.
CLAUDE_FABLE_5_THINKING_PROFILE: dict[str, Any] = {
    "levels": [
        {"id": "off"},
        {"id": "minimal"},
        {"id": "low"},
        {"id": "medium"},
        {"id": "high"},
        {"id": "xhigh"},
        {"id": "adaptive"},
        {"id": "max"},
    ],
    "defaultLevel": "high",
    "preserveWhenCatalogReasoningFalse": True,
}

#: Parity: ``CLAUDE_SONNET_5_THINKING_PROFILE``. Same levels as Fable 5 but
#: *without* the preserve flag — that asymmetry is in the TS and is kept.
CLAUDE_SONNET_5_THINKING_PROFILE: dict[str, Any] = {
    "levels": [
        {"id": "off"},
        {"id": "minimal"},
        {"id": "low"},
        {"id": "medium"},
        {"id": "high"},
        {"id": "xhigh"},
        {"id": "adaptive"},
        {"id": "max"},
    ],
    "defaultLevel": "high",
}


# ─────────────────────────────────────────────────────────────────────
# Normalization
# ─────────────────────────────────────────────────────────────────────

_ANTHROPIC_PREFIX = "anthropic/"

#: Parity: ``/[._\\s]+/g``. Dots, underscores and whitespace all collapse to
#: a single hyphen so ``claude_fable_5`` and ``claude.fable.5`` normalize the
#: same way as ``claude-fable-5``.
_SEPARATORS = re.compile(r"[._\s]+")

#: Parity: ``/(?:^|[-/])claude-/``. Finds where the vendor-agnostic model
#: name starts inside a longer deployment identifier.
_CLAUDE_ANCHOR = re.compile(r"(?:^|[-/])claude-")


def _normalize_claude_model_id(model_id: str | None) -> str:
    """Parity: ``normalizeClaudeModelId``.

    Returns ``""`` for ``None``, mirroring ``modelId?.trim()... ?? ""``.
    """
    normalized = (model_id or "").strip().lower()
    unprefixed = (
        normalized[len(_ANTHROPIC_PREFIX) :]
        if normalized.startswith(_ANTHROPIC_PREFIX)
        else normalized
    )
    return _SEPARATORS.sub("-", unprefixed)


def resolve_claude_model_identity(ref: ClaudeModelRef) -> str:
    """Canonical normalized Claude model id. Parity: ``resolveClaudeModelIdentity``.

    ``params["canonicalModelId"]`` wins over ``id`` when it is a string,
    which is how a gateway pins the true model behind an opaque alias. The
    wire key stays camelCase because it is read from persisted config.
    """
    params = getattr(ref, "params", None)
    configured = params.get("canonicalModelId") if isinstance(params, dict) else None
    if not isinstance(configured, str):
        configured = None

    normalized = _normalize_claude_model_id(
        configured if configured is not None else getattr(ref, "id", None)
    )
    match = _CLAUDE_ANCHOR.search(normalized)
    if match is None:
        return normalized
    # The anchor may include a leading "-" or "/"; drop it, keep "claude-".
    offset = 0 if match.group(0).startswith("claude-") else 1
    return normalized[match.start() + offset :]


def _resolve_family(normalized: str, family: str) -> str | None:
    """Shared body of the ``resolve_claude_*_identity`` functions.

    Parity: each TS function inlines this. The lookahead
    ``(?=$|[^a-z0-9])`` is what stops ``claude-sonnet-55`` from matching
    ``claude-sonnet-5`` — a boundary check that ``str.startswith`` cannot
    express, which is why these stay regexes.
    """
    match = re.search(rf"(?:^|-){re.escape(family)}(?=$|[^a-z0-9])", normalized)
    if match is None:
        return None
    offset = 1 if match.group(0).startswith("-") else 0
    return normalized[match.start() + offset :]


def resolve_claude_fable5_model_identity(ref: ClaudeModelRef) -> str | None:
    """Parity: ``resolveClaudeFable5ModelIdentity``."""
    return _resolve_family(resolve_claude_model_identity(ref), "claude-fable-5")


def resolve_claude_mythos5_model_identity(ref: ClaudeModelRef) -> str | None:
    """Parity: ``resolveClaudeMythos5ModelIdentity``."""
    return _resolve_family(resolve_claude_model_identity(ref), "claude-mythos-5")


def resolve_claude_sonnet5_model_identity(ref: ClaudeModelRef) -> str | None:
    """Parity: ``resolveClaudeSonnet5ModelIdentity``."""
    return _resolve_family(resolve_claude_model_identity(ref), "claude-sonnet-5")


# ─────────────────────────────────────────────────────────────────────
# Capability predicates
# ─────────────────────────────────────────────────────────────────────

_MYTHOS_PREVIEW = re.compile(r"(?:^|-)claude-mythos-preview(?=$|[^a-z0-9])")

_ADAPTIVE_THINKING = re.compile(
    r"(?:^|-)claude-(?:fable-5|mythos-(?:5|preview)|opus-4-(?:6|7|8)|sonnet-(?:5|4-6))"
    r"(?=$|[^a-z0-9])"
)

_NATIVE_MAX_EFFORT = re.compile(
    r"(?:^|-)claude-(?:fable-5|mythos-5|opus-4-(?:6|7|8)|sonnet-(?:5|4-6))(?=$|[^a-z0-9])"
)

_NATIVE_XHIGH_EFFORT = re.compile(
    r"(?:^|-)claude-(?:fable-5|mythos-5|opus-4-(?:7|8)|sonnet-5)(?=$|[^a-z0-9])"
)


def requires_claude_mandatory_adaptive_thinking(ref: ClaudeModelRef) -> bool:
    """Parity: ``requiresClaudeMandatoryAdaptiveThinking``.

    These models reject manual token budgets, so sending one is a hard
    provider error rather than a degraded response.
    """
    model_id = resolve_claude_model_identity(ref)
    return (
        resolve_claude_fable5_model_identity(ref) is not None
        or resolve_claude_mythos5_model_identity(ref) is not None
        or _MYTHOS_PREVIEW.search(model_id) is not None
    )


def supports_claude_adaptive_thinking(ref: ClaudeModelRef) -> bool:
    """Parity: ``supportsClaudeAdaptiveThinking``."""
    return _ADAPTIVE_THINKING.search(resolve_claude_model_identity(ref)) is not None


def supports_claude_native_max_effort(ref: ClaudeModelRef) -> bool:
    """Parity: ``supportsClaudeNativeMaxEffort``."""
    return _NATIVE_MAX_EFFORT.search(resolve_claude_model_identity(ref)) is not None


def supports_claude_native_xhigh_effort(ref: ClaudeModelRef) -> bool:
    """Parity: ``supportsClaudeNativeXhighEffort``.

    Note the family list is *narrower* than max effort: opus-4-6 supports
    max but not xhigh. Collapsing the two regexes into one would quietly
    send an unsupported effort value.
    """
    return _NATIVE_XHIGH_EFFORT.search(resolve_claude_model_identity(ref)) is not None


def requires_claude_default_sampling(ref: ClaudeModelRef) -> bool:
    """Parity: ``requiresClaudeDefaultSampling``.

    When true, caller-selected ``temperature``/``top_p`` must be omitted —
    these models reject them outright.
    """
    model_id = resolve_claude_model_identity(ref)
    return (
        supports_claude_native_xhigh_effort(ref) or _MYTHOS_PREVIEW.search(model_id) is not None
    )


def resolve_claude_native_thinking_level_map(
    ref: ClaudeEffortModelRef,
) -> dict[str, str | None] | None:
    """Parity: ``resolveClaudeNativeThinkingLevelMap``.

    A provider-published map always wins; this only fills the gap when the
    catalog published nothing. The check is ``is not None``, not
    truthiness: an explicitly published empty map means "this model maps no
    levels natively" and must not be overwritten with defaults.

    The ``None`` value for ``xhigh`` is meaningful — it marks the level
    *unsupported*, which is different from absent (use provider default).
    """
    published = getattr(ref, "thinking_level_map", None)
    if published is not None:
        return published
    if not supports_claude_native_max_effort(ref):
        return None
    return {
        "xhigh": "xhigh" if supports_claude_native_xhigh_effort(ref) else None,
        "max": "max",
    }


__all__ = [
    "CLAUDE_FABLE_5_THINKING_PROFILE",
    "CLAUDE_SONNET_5_THINKING_PROFILE",
    "ClaudeEffortModelRef",
    "ClaudeModelRef",
    "requires_claude_default_sampling",
    "requires_claude_mandatory_adaptive_thinking",
    "resolve_claude_fable5_model_identity",
    "resolve_claude_model_identity",
    "resolve_claude_mythos5_model_identity",
    "resolve_claude_native_thinking_level_map",
    "resolve_claude_sonnet5_model_identity",
    "supports_claude_adaptive_thinking",
    "supports_claude_native_max_effort",
    "supports_claude_native_xhigh_effort",
]
