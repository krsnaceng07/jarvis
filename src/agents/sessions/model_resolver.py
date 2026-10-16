"""jarvis.agents.sessions.model_resolver — model resolution + scoping.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/model-resolver.ts``.

Model resolution, scoping, and initial
selection. Supports:
- ``findExactModelReferenceMatch`` —
  exact ``provider/modelId`` or bare-id match.
- ``parseModelPattern`` — parse a
  ``"model:thinking_level"`` pattern (handles
  models with colons in their IDs).
- ``resolveModelScope`` (async) — glob
  + exact scope resolver.
- ``resolveCliModel`` — CLI ``--provider``
  + ``--model`` resolver.
- ``findInitialModel`` (async) — initial
  model priority resolver (CLI → scoped
  → restored → saved default → first
  available).

Phase 6.7c — model resolver.

Adaptations
-----------
- The OpenClaw source uses the npm
  ``minimatch`` package. The Python port
  ships a minimal :func:`_glob_match`
  helper (supports ``*`` + ``?`` + ``[abc]``)
  that covers the patterns the source
  actually uses.
- The OpenClaw source uses the npm
  ``chalk`` package for terminal colors.
  The Python port strips colors (the
  OpenClaw warning texts are returned as
  plain strings; the caller can colourise
  as needed).
- The OpenClaw source's
  ``modelsAreEqual`` from
  ``@openclaw/ai/internal/runtime`` is
  replaced with a Python helper that
  compares on ``(provider, id)``.
- The OpenClaw source's TS interfaces
  (``ScopedModel``,
  ``ParsedModelResult``,
  ``ResolveCliModelResult``,
  ``InitialModelResult``) are replaced
  with plain ``dict`` shapes (the
  OpenClaw-shape preserved via the
  ``__all__`` re-exports).
- The OpenClaw source's
  ``process.exit(1)`` on CLI errors is
  replaced with an ``error`` field on
  the result (the CLI wiring lands in
  6.10+ with the tools layer).
"""
from __future__ import annotations

import fnmatch
import logging
import re
from typing import Optional

from .defaults import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_THINKING_LEVEL,
    ThinkingLevel,
)
from .model_registry import Model, ModelRegistry


_LOG = logging.getLogger("jarvis.agents.sessions.model_resolver")


# ============================================================================
# Thinking-level constants
# ============================================================================


#: Mirrors ``VALID_THINKING_LEVELS``
#: (``model-resolver.ts:14``). The Python
#: port uses a ``frozenset`` for O(1) lookups.
VALID_THINKING_LEVELS: frozenset = frozenset(
    {"off", "minimal", "low", "medium", "high", "xhigh", "max"}
)


def _is_valid_thinking_level(level: str) -> bool:
    """True iff ``level`` is a known thinking
    level. Mirrors ``isValidThinkingLevel``
    (``model-resolver.ts:16-18``)."""
    return level in VALID_THINKING_LEVELS


# ============================================================================
# Public types
# ============================================================================


#: Mirrors ``ScopedModel``
#: (``model-resolver.ts:20-24``).
#: ``{"model", "thinkingLevel"?}``.
ScopedModel = dict


#: Mirrors ``ParsedModelResult``
#: (``model-resolver.ts:127-132``).
#: ``{"model"?, "thinkingLevel"?,
#: "warning"?}``.
ParsedModelResult = dict


#: Mirrors ``ResolveCliModelResult``
#: (``model-resolver.ts:308-317``).
#: ``{"model"?, "thinkingLevel"?,
#: "warning"?, "error"?}``.
ResolveCliModelResult = dict


#: Mirrors ``InitialModelResult``
#: (``model-resolver.ts:488-492``).
#: ``{"model"?, "thinkingLevel",
#: "fallbackMessage"?}``.
InitialModelResult = dict


# ============================================================================
# Helpers
# ============================================================================


def _is_alias(model_id: str) -> bool:
    """True iff ``model_id`` looks like an alias
    (no date suffix). Mirrors ``isAlias``
    (``model-resolver.ts:30-39``).

    Dates are typically in format:
    ``-20241022`` or ``-20250929``.
    """
    if model_id.endswith("-latest"):
        return True
    date_pattern = re.compile(r"-\d{8}$")
    return not bool(date_pattern.search(model_id))


def _glob_match(pattern: str, text: str) -> bool:
    """Glob match. Mirrors the OpenClaw source's
    use of the npm ``minimatch`` package
    (``model-resolver.ts:270-272``).

    The Python port uses :func:`fnmatch.fnmatch`
    (which supports ``*``, ``?``, ``[abc]``) +
    a case-insensitive flag (the OpenClaw
    source's ``{ nocase: true }``)."""
    return fnmatch.fnmatchcase(text.lower(), pattern.lower())


def _models_are_equal(a: Model, b: Model) -> bool:
    """True iff two :class:`Model` rows are the
    same. Mirrors the OpenClaw source's
    ``modelsAreEqual``
    (``@openclaw/ai/internal/runtime``)."""
    return a.get("provider") == b.get("provider") and a.get("id") == b.get("id")


# ============================================================================
# findExactModelReferenceMatch
# ============================================================================


def find_exact_model_reference_match(
    model_reference: str,
    available_models: list[Model],
) -> Optional[Model]:
    """Find an exact model reference match.
    Mirrors ``findExactModelReferenceMatch``
    (``model-resolver.ts:46-90``).

    Supports either a bare model id or a
    canonical ``provider/modelId`` reference.
    When matching by bare id, ambiguous matches
    across providers are rejected.
    """
    trimmed = (model_reference or "").strip()
    if not trimmed:
        return None
    normalized = trimmed.lower()
    canonical_matches = [
        m
        for m in available_models
        if f"{m.get('provider')}/{m.get('id')}".lower() == normalized
    ]
    if len(canonical_matches) == 1:
        return canonical_matches[0]
    if len(canonical_matches) > 1:
        return None
    slash_index = trimmed.find("/")
    if slash_index != -1:
        provider = trimmed[:slash_index].strip()
        model_id = trimmed[slash_index + 1 :].strip()
        if provider and model_id:
            provider_matches = [
                m
                for m in available_models
                if m.get("provider", "").lower() == provider.lower()
                and m.get("id", "").lower() == model_id.lower()
            ]
            if len(provider_matches) == 1:
                return provider_matches[0]
            if len(provider_matches) > 1:
                return None
    id_matches = [
        m for m in available_models if m.get("id", "").lower() == normalized
    ]
    if len(id_matches) == 1:
        return id_matches[0]
    return None


# ============================================================================
# tryMatchModel + parseModelPattern
# ============================================================================


def _try_match_model(
    model_pattern: str, available_models: list[Model]
) -> Optional[Model]:
    """Try to match a pattern to a model. Mirrors
    ``tryMatchModel``
    (``model-resolver.ts:96-125``).

    Returns the matched model or ``None`` if
    no match is found. The algorithm:
    1. Try exact match (canonical or bare id).
    2. Fall back to partial id / name match.
       Prefer aliases (no date suffix) over
       dated versions; otherwise pick the
       latest dated version.
    """
    exact = find_exact_model_reference_match(
        model_pattern, available_models
    )
    if exact:
        return exact
    pattern_lower = model_pattern.lower()
    matches = [
        m
        for m in available_models
        if pattern_lower in (m.get("id", "").lower())
        or pattern_lower in ((m.get("name") or "").lower())
    ]
    if not matches:
        return None
    aliases = [m for m in matches if _is_alias(m.get("id", ""))]
    dated_versions = [m for m in matches if not _is_alias(m.get("id", ""))]
    if aliases:
        aliases.sort(
            key=lambda m: m.get("id", ""),
            reverse=True,
        )
        return aliases[0]
    dated_versions.sort(
        key=lambda m: m.get("id", ""),
        reverse=True,
    )
    return dated_versions[0] if dated_versions else None


def parse_model_pattern(
    pattern: str,
    available_models: list[Model],
    options: Optional[dict] = None,
) -> ParsedModelResult:
    """Parse a pattern to extract the model +
    thinking level. Mirrors
    ``parseModelPattern``
    (``model-resolver.ts:177-229``).

    Handles models with colons in their ids
    (e.g., OpenRouter's ``:exacto`` suffix).
    The algorithm:
    1. Try exact match (full pattern).
    2. If not found and the pattern has
       colons, split on the last colon: if the
       suffix is a valid thinking level, use
       it and recurse on the prefix; otherwise
       warn and recurse on the prefix with
       ``"off"``.
    """
    options = options or {}
    exact = _try_match_model(pattern, available_models)
    if exact:
        return {
            "model": exact,
            "thinkingLevel": None,
            "warning": None,
        }
    last_colon = pattern.rfind(":")
    if last_colon == -1:
        return {
            "model": None,
            "thinkingLevel": None,
            "warning": None,
        }
    prefix = pattern[:last_colon]
    suffix = pattern[last_colon + 1 :]
    if _is_valid_thinking_level(suffix):
        result = parse_model_pattern(prefix, available_models, options)
        if result.get("model"):
            return {
                "model": result["model"],
                "thinkingLevel": (
                    suffix if not result.get("warning") else None
                ),
                "warning": result.get("warning"),
            }
        return result
    allow_fallback = options.get(
        "allowInvalidThinkingLevelFallback", True
    )
    if not allow_fallback:
        return {
            "model": None,
            "thinkingLevel": None,
            "warning": None,
        }
    result = parse_model_pattern(prefix, available_models, options)
    if result.get("model"):
        return {
            "model": result["model"],
            "thinkingLevel": None,
            "warning": (
                f'Invalid thinking level "{suffix}" in pattern '
                f'"{pattern}". Using default instead.'
            ),
        }
    return result


# ============================================================================
# buildFallbackModel + selectAvailableFallbackModel
# ============================================================================


def _build_fallback_model(
    provider: str,
    model_id: str,
    available_models: list[Model],
) -> Optional[Model]:
    """Build a fallback :class:`Model` row for a
    provider. Mirrors ``buildFallbackModel``
    (``model-resolver.ts:134-154``)."""
    provider_models = [
        m for m in available_models if m.get("provider") == provider
    ]
    if not provider_models:
        return None
    base_model = provider_models[0]
    return {**base_model, "id": model_id, "name": model_id}


def _select_available_fallback_model(
    available_models: list[Model],
) -> Optional[Model]:
    """Pick the first available fallback model.
    Mirrors ``selectAvailableFallbackModel``
    (``model-resolver.ts:156-162``)."""
    for m in available_models:
        if (
            m.get("provider") == DEFAULT_PROVIDER
            and m.get("id") == DEFAULT_MODEL
        ):
            return m
    return available_models[0] if available_models else None


# ============================================================================
# resolveModelScope
# ============================================================================


async def resolve_model_scope(
    patterns: list[str],
    model_registry: ModelRegistry,
) -> list[ScopedModel]:
    """Resolve model patterns to actual
    :class:`Model` objects. Mirrors
    ``resolveModelScope``
    (``model-resolver.ts:242-306``).

    Each pattern can be a glob (``*``, ``?``,
    ``[...]``) or an exact id. Patterns may
    include an optional ``:thinking_level``
    suffix. Duplicate models are removed.
    """
    available = model_registry.get_available()
    scoped: list[ScopedModel] = []
    for pattern in patterns:
        # Glob → match against
        # ``provider/modelId`` or just modelId.
        if any(c in pattern for c in ("*", "?", "[")):
            colon_idx = pattern.rfind(":")
            glob_pattern = pattern
            thinking_level: Optional[ThinkingLevel] = None
            if colon_idx != -1:
                suffix = pattern[colon_idx + 1 :]
                if _is_valid_thinking_level(suffix):
                    thinking_level = suffix
                    glob_pattern = pattern[:colon_idx]
            matches = [
                m
                for m in available
                if _glob_match(glob_pattern, f"{m.get('provider')}/{m.get('id')}")
                or _glob_match(glob_pattern, m.get("id", ""))
            ]
            if not matches:
                _LOG.warning(
                    "Warning: No models match pattern %r", pattern
                )
                continue
            for m in matches:
                if not any(_models_are_equal(sm["model"], m) for sm in scoped):
                    scoped.append(
                        {"model": m, "thinkingLevel": thinking_level}
                    )
            continue
        # Exact / partial match.
        result = parse_model_pattern(pattern, available)
        if result.get("warning"):
            _LOG.warning("Warning: %s", result["warning"])
        if not result.get("model"):
            _LOG.warning(
                "Warning: No models match pattern %r", pattern
            )
            continue
        model = result["model"]
        if not any(_models_are_equal(sm["model"], model) for sm in scoped):
            scoped.append(
                {
                    "model": model,
                    "thinkingLevel": result.get("thinkingLevel"),
                }
            )
    return scoped


# ============================================================================
# resolveCliModel
# ============================================================================


def resolve_cli_model(options: dict) -> ResolveCliModelResult:
    """Resolve a single model from CLI flags.
    Mirrors ``resolveCliModel``
    (``model-resolver.ts:330-486``).
    """
    cli_provider = options.get("cliProvider")
    cli_model = options.get("cliModel")
    cli_thinking = options.get("cliThinking")
    model_registry: ModelRegistry = options["modelRegistry"]
    if not cli_model:
        return {
            "model": None,
            "thinkingLevel": None,
            "warning": None,
            "error": None,
        }
    available = model_registry.get_all()
    if not available:
        return {
            "model": None,
            "thinkingLevel": None,
            "warning": None,
            "error": (
                "No models available. Check your installation or "
                "add models to models.json."
            ),
        }
    # Build the canonical provider lookup.
    provider_map: dict[str, str] = {}
    for m in available:
        provider_map[m.get("provider", "").lower()] = m.get("provider", "")
    provider = (
        provider_map.get(cli_provider.lower())
        if cli_provider
        else None
    )
    if cli_provider and not provider:
        return {
            "model": None,
            "thinkingLevel": None,
            "warning": None,
            "error": (
                f'Unknown provider "{cli_provider}". Use '
                "--list-models to see available providers/models."
            ),
        }
    pattern = cli_model
    inferred_provider = False
    if not provider:
        slash_index = cli_model.find("/")
        if slash_index != -1:
            maybe_provider = cli_model[:slash_index]
            canonical = provider_map.get(maybe_provider.lower())
            if canonical:
                provider = canonical
                pattern = cli_model[slash_index + 1 :]
                inferred_provider = True
    if not provider:
        lower = cli_model.lower()
        exact = next(
            (
                m
                for m in available
                if m.get("id", "").lower() == lower
                or f"{m.get('provider')}/{m.get('id')}".lower() == lower
            ),
            None,
        )
        if exact:
            return {
                "model": exact,
                "thinkingLevel": None,
                "warning": None,
                "error": None,
            }
    if cli_provider and provider:
        prefix = f"{provider}/"
        if cli_model.lower().startswith(prefix.lower()):
            pattern = cli_model[len(prefix) :]
    candidates = (
        [m for m in available if m.get("provider") == provider]
        if provider
        else available
    )
    parsed = parse_model_pattern(
        pattern, candidates, {"allowInvalidThinkingLevelFallback": False}
    )
    if parsed.get("model"):
        return {
            "model": parsed["model"],
            "thinkingLevel": parsed.get("thinkingLevel"),
            "warning": parsed.get("warning"),
            "error": None,
        }
    if inferred_provider:
        lower = cli_model.lower()
        exact = next(
            (
                m
                for m in available
                if m.get("id", "").lower() == lower
                or f"{m.get('provider')}/{m.get('id')}".lower() == lower
            ),
            None,
        )
        if exact:
            return {
                "model": exact,
                "thinkingLevel": None,
                "warning": None,
                "error": None,
            }
        fallback = parse_model_pattern(
            cli_model, available, {"allowInvalidThinkingLevelFallback": False}
        )
        if fallback.get("model"):
            return {
                "model": fallback["model"],
                "thinkingLevel": fallback.get("thinkingLevel"),
                "warning": fallback.get("warning"),
                "error": None,
            }
    if provider:
        fallback_pattern = pattern
        fallback_thinking: Optional[ThinkingLevel] = None
        if not cli_thinking:
            last_colon = fallback_pattern.rfind(":")
            if last_colon != -1:
                suffix = fallback_pattern[last_colon + 1 :]
                if _is_valid_thinking_level(suffix):
                    fallback_pattern = fallback_pattern[:last_colon]
                    fallback_thinking = suffix
        fallback_model = _build_fallback_model(
            provider, fallback_pattern, available
        )
        if fallback_model:
            requested_thinking = cli_thinking or fallback_thinking
            resolved_model = (
                {**fallback_model, "reasoning": True}
                if requested_thinking and requested_thinking != "off"
                else fallback_model
            )
            base_warning = parsed.get("warning")
            fallback_warning = (
                f"{base_warning} Model \"{fallback_pattern}\" not found for "
                f"provider \"{provider}\". Using custom model id."
                if base_warning
                else f"Model \"{fallback_pattern}\" not found for provider "
                f"\"{provider}\". Using custom model id."
            )
            return {
                "model": resolved_model,
                "thinkingLevel": requested_thinking,
                "warning": fallback_warning,
                "error": None,
            }
    display = (
        f"{provider}/{pattern}" if provider else cli_model
    )
    return {
        "model": None,
        "thinkingLevel": None,
        "warning": parsed.get("warning"),
        "error": (
            f'Model "{display}" not found. Use --list-models to '
            "see available models."
        ),
    }


# ============================================================================
# findInitialModel
# ============================================================================


async def find_initial_model(options: dict) -> InitialModelResult:
    """Find the initial model to use based on
    priority. Mirrors ``findInitialModel``
    (``model-resolver.ts:502-584``).

    Priority:
    1. CLI args (``cliProvider`` + ``cliModel``).
    2. First model from scoped models (if not
       continuing/resuming).
    3. Saved default from settings (if auth
       configured).
    4. First available model with valid API
       key.
    5. ``undefined`` (no model found).
    """
    cli_provider = options.get("cliProvider")
    cli_model = options.get("cliModel")
    scoped_models: list[ScopedModel] = options.get("scopedModels", [])
    is_continuing: bool = bool(options.get("isContinuing"))
    default_provider = options.get("defaultProvider")
    default_model_id = options.get("defaultModelId")
    default_thinking_level = options.get("defaultThinkingLevel")
    model_registry: ModelRegistry = options["modelRegistry"]

    model: Optional[Model] = None
    thinking_level: ThinkingLevel = DEFAULT_THINKING_LEVEL
    # 1. CLI args.
    if cli_provider and cli_model:
        resolved = resolve_cli_model(
            {
                "cliProvider": cli_provider,
                "cliModel": cli_model,
                "modelRegistry": model_registry,
            }
        )
        if resolved.get("error"):
            raise RuntimeError(resolved["error"])
        if resolved.get("model"):
            return {
                "model": resolved["model"],
                "thinkingLevel": (
                    resolved.get("thinkingLevel")
                    or DEFAULT_THINKING_LEVEL
                ),
                "fallbackMessage": None,
            }
    # 2. Scoped models.
    if scoped_models and not is_continuing:
        first = scoped_models[0]
        return {
            "model": first["model"],
            "thinkingLevel": (
                first.get("thinkingLevel")
                or default_thinking_level
                or DEFAULT_THINKING_LEVEL
            ),
            "fallbackMessage": None,
        }
    # 3. Saved default.
    if default_provider and default_model_id:
        found = model_registry.find(default_provider, default_model_id)
        if found and model_registry.has_configured_auth(found):
            model = found
            if default_thinking_level:
                thinking_level = default_thinking_level
            return {
                "model": model,
                "thinkingLevel": thinking_level,
                "fallbackMessage": None,
            }
    # 4. First available model.
    available = model_registry.get_available()
    if available:
        return {
            "model": _select_available_fallback_model(available),
            "thinkingLevel": DEFAULT_THINKING_LEVEL,
            "fallbackMessage": None,
        }
    # 5. No model found.
    return {
        "model": None,
        "thinkingLevel": DEFAULT_THINKING_LEVEL,
        "fallbackMessage": None,
    }


__all__ = [
    "InitialModelResult",
    "ParsedModelResult",
    "ResolveCliModelResult",
    "ScopedModel",
    "VALID_THINKING_LEVELS",
    "find_exact_model_reference_match",
    "find_initial_model",
    "parse_model_pattern",
    "resolve_cli_model",
    "resolve_model_scope",
]
