"""Provider model-id normalization policies (manifest + built-in).

OpenClaw parity:
``packages/model-catalog-core/src/provider-model-id-normalization.ts``.
Manifest policies come from plugin manifests (``modelIdNormalization``);
built-in rules cover provider-owned renames. Manifest policies apply
first, built-ins second. The process-local policy snapshot is a
single-slot lifecycle-owned cache: the host replaces it on
reload/install and readers never freshness-poll manifests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_normalization_core.string_coerce import normalize_lowercase_string_or_empty

from .model_catalog_refs import parse_model_catalog_ref
from .provider_model_id_normalize import (
    normalize_google_preview_model_id,
    normalize_together_model_id,
)


@dataclass(frozen=True, slots=True)
class PrefixWhenBareAfterAliasRule:
    """Prefix a bare model id when it starts with ``model_prefix`` (post-alias)."""

    model_prefix: str = ""
    prefix: str = ""


@dataclass(frozen=True, slots=True)
class ManifestModelIdNormalizationProvider:
    """Manifest-defined normalization rules for one provider."""

    aliases: dict[str, str] = field(default_factory=dict)
    strip_prefixes: tuple[str, ...] = field(default_factory=tuple)
    prefix_when_bare: str | None = None
    prefix_when_bare_after_alias_starts_with: tuple[PrefixWhenBareAfterAliasRule, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True, slots=True)
class ModelIdNormalizationPolicies:
    """Collected manifest normalization policies keyed by normalized provider."""

    providers: dict[str, ManifestModelIdNormalizationProvider] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ManifestModelIdNormalizationRecord:
    """Manifest fragment carrying provider model-id normalization policies.

    Mirrors ``ManifestModelIdNormalizationRecord`` (the ``modelIdNormalization``
    block); :func:`collect_manifest_model_id_normalization_policies` accepts
    either these records or raw manifest dicts.
    """

    providers: dict[str, ManifestModelIdNormalizationProvider] = field(default_factory=dict)


def collect_manifest_model_id_normalization_policies(
    plugins: list[dict[str, Any] | ManifestModelIdNormalizationRecord],
) -> ModelIdNormalizationPolicies:
    """Collect ``modelIdNormalization`` policies from plugin manifests."""
    providers: dict[str, ManifestModelIdNormalizationProvider] = {}
    for plugin in plugins:
        if isinstance(plugin, ManifestModelIdNormalizationRecord):
            for provider, policy in plugin.providers.items():
                providers[normalize_lowercase_string_or_empty(provider)] = policy
            continue
        if not isinstance(plugin, dict):
            continue
        manifest_block: dict[str, Any] = plugin
        if not isinstance(manifest_block.get("modelIdNormalization"), dict):
            continue
        record: dict[str, Any] = manifest_block.get("modelIdNormalization") or {}
        if not isinstance(record.get("providers"), dict):
            continue
        entries: dict[str, Any] = record.get("providers") or {}
        provider_policies: dict[str, Any] = entries
        for provider, policy in provider_policies.items():
            if not isinstance(policy, dict):
                continue
            rule: dict[str, Any] = policy
            aliases = rule.get("aliases")
            strip_prefixes = (
                rule.get("stripPrefixes") if isinstance(rule.get("stripPrefixes"), list) else []
            )
            prefix_when_bare = rule.get("prefixWhenBare")
            rules: list[PrefixWhenBareAfterAliasRule] = []
            if isinstance(rule.get("prefixWhenBareAfterAliasStartsWith"), list):
                raw_rules: list[Any] = rule.get("prefixWhenBareAfterAliasStartsWith") or []
                for raw_rule in raw_rules:
                    if not isinstance(raw_rule, dict):
                        continue
                    model_prefix = raw_rule.get("modelPrefix")
                    prefix = raw_rule.get("prefix")
                    if isinstance(model_prefix, str) and isinstance(prefix, str):
                        rules.append(
                            PrefixWhenBareAfterAliasRule(model_prefix=model_prefix, prefix=prefix)
                        )
            providers[normalize_lowercase_string_or_empty(provider)] = (
                ManifestModelIdNormalizationProvider(
                    aliases=dict(aliases) if isinstance(aliases, dict) else {},
                    strip_prefixes=tuple(p for p in strip_prefixes if isinstance(p, str))
                    if isinstance(strip_prefixes, list)
                    else (),
                    prefix_when_bare=prefix_when_bare
                    if isinstance(prefix_when_bare, str)
                    else None,
                    prefix_when_bare_after_alias_starts_with=tuple(rules),
                )
            )
    return ModelIdNormalizationPolicies(providers=providers)


#: Process-local manifest policy snapshot. Replaced wholesale by the host
#: on reload/install; never mutated in place, never re-read per call.
_current_policies: ModelIdNormalizationPolicies | None = None


def set_current_manifest_model_id_normalization_policies(
    policies: ModelIdNormalizationPolicies | None,
) -> None:
    """Replace the process-local manifest normalization policy snapshot."""
    global _current_policies
    _current_policies = policies


def _has_provider_prefix(model_id: str) -> bool:
    return "/" in model_id


def _format_prefixed_model_id(prefix: str, model_id: str) -> str:
    return f"{prefix.rstrip('/')}/{model_id.lstrip('/')}"


def strip_self_provider_model_prefix(provider: str, model: str) -> str:
    """Strip a duplicated self-provider prefix (``openai/openai/gpt`` → ``openai/gpt``)."""
    prefix = f"{normalize_lowercase_string_or_empty(provider)}/"
    trimmed = model.strip()
    if normalize_lowercase_string_or_empty(trimmed).startswith(prefix):
        return trimmed[len(prefix) :]
    return model


def normalize_provider_model_id_with_policies(
    provider: str,
    model_id: str,
    policies: ModelIdNormalizationPolicies,
) -> str | None:
    """Apply manifest normalization policies; ``None`` when no policy exists."""
    policy = policies.providers.get(normalize_lowercase_string_or_empty(provider))
    if policy is None:
        return None
    current = model_id.strip()
    if not current:
        return current
    for prefix in policy.strip_prefixes:
        normalized_prefix = normalize_lowercase_string_or_empty(prefix)
        if normalized_prefix and normalize_lowercase_string_or_empty(current).startswith(
            normalized_prefix
        ):
            current = current[len(normalized_prefix) :]
            break
    current = policy.aliases.get(normalize_lowercase_string_or_empty(current), current)
    if not _has_provider_prefix(current):
        for rule in policy.prefix_when_bare_after_alias_starts_with:
            if normalize_lowercase_string_or_empty(current).startswith(rule.model_prefix.lower()):
                return _format_prefixed_model_id(rule.prefix, current)
        if policy.prefix_when_bare:
            return _format_prefixed_model_id(policy.prefix_when_bare, current)
    return current


_ANTHROPIC_ALIASES = {
    "opus-5": "claude-opus-5",
    "opus": "claude-opus-5",
    "opus-4.8": "claude-opus-4-8",
    "opus-4.6": "claude-opus-4-6",
    "sonnet-5": "claude-sonnet-5",
    "sonnet": "claude-sonnet-5",
    "sonnet-4.6": "claude-sonnet-4-6",
}

_VERCEL_ALIASES = {
    "opus-4.6": "claude-opus-4-6",
    "sonnet-5": "claude-sonnet-5",
    "sonnet": "claude-sonnet-4-6",
    "sonnet-4.6": "claude-sonnet-4-6",
}

_XAI_ALIASES = {
    "grok-4.3-latest": "grok-4.3",
    "grok-4.5-latest": "grok-4.5",
    "grok-build-latest": "grok-4.5",
    "grok-4-fast-reasoning": "grok-4-fast",
    "grok-4-1-fast-reasoning": "grok-4-1-fast",
}


def normalize_builtin_provider_model_id(provider: str, model: str) -> str:
    """Apply built-in provider-specific model-id normalization rules."""
    normalized_provider = normalize_lowercase_string_or_empty(provider)
    if normalized_provider in ("google", "google-gemini-cli", "google-vertex"):
        return normalize_google_preview_model_id(model)
    if normalized_provider == "openrouter":
        trimmed = model.strip()
        return f"openrouter/{trimmed}" if trimmed and "/" not in trimmed else model
    if normalized_provider == "anthropic":
        prefix = "anthropic/"
        bare = (
            model.strip()[len(prefix) :]
            if normalize_lowercase_string_or_empty(model).startswith(prefix)
            else model
        )
        return _ANTHROPIC_ALIASES.get(normalize_lowercase_string_or_empty(bare), bare)
    if normalized_provider == "vercel-ai-gateway":
        aliased = _VERCEL_ALIASES.get(normalize_lowercase_string_or_empty(model), model)
        return (
            f"anthropic/{aliased}"
            if normalize_lowercase_string_or_empty(aliased).startswith("claude-")
            else aliased
        )
    if normalized_provider == "huggingface":
        prefix = "huggingface/"
        return (
            model[len(prefix) :]
            if normalize_lowercase_string_or_empty(model).startswith(prefix)
            else model
        )
    if normalized_provider == "nvidia":
        trimmed = model.strip()
        return f"nvidia/{trimmed}" if trimmed and "/" not in trimmed else model
    if normalized_provider == "xai":
        return _XAI_ALIASES.get(normalize_lowercase_string_or_empty(model), model)
    if normalized_provider == "openai":
        return model
    if normalized_provider == "together":
        return normalize_together_model_id(model)
    return model


def normalize_static_provider_model_id_with_policies(
    provider: str,
    model: str,
    policies: ModelIdNormalizationPolicies | None = None,
) -> str:
    """Apply manifest policies then built-in rules to a static provider/model id."""
    normalized_provider = normalize_lowercase_string_or_empty(provider)
    manifest_model_id = (
        normalize_provider_model_id_with_policies(normalized_provider, model, policies)
        if policies is not None
        else None
    )
    return normalize_builtin_provider_model_id(
        normalized_provider, manifest_model_id if manifest_model_id is not None else model
    )


def normalize_configured_provider_catalog_model_ref(provider_model: str) -> str:
    """Normalize embedded Google model aliases inside catalog refs."""
    google_prefix = "google/"
    if not provider_model.startswith(google_prefix):
        parsed = parse_model_catalog_ref(provider_model)
        if parsed is None or not parsed.model_id.startswith(google_prefix):
            return provider_model
        normalized = normalize_google_preview_model_id(parsed.model_id)
        return (
            provider_model if normalized == parsed.model_id else f"{parsed.provider}/{normalized}"
        )
    model_id = provider_model[len(google_prefix) :]
    normalized = normalize_google_preview_model_id(model_id)
    return provider_model if normalized == model_id else f"{google_prefix}{normalized}"


def normalize_configured_provider_catalog_model_id(
    provider: str,
    model: str,
    policies: ModelIdNormalizationPolicies | None = None,
) -> str:
    """Normalize a configured provider/model id using current policies."""
    if policies is None:
        policies = _current_policies
    static_id = (
        normalize_static_provider_model_id_with_policies(provider, model, policies)
        if policies is not None
        else normalize_builtin_provider_model_id(provider, model)
    )
    return normalize_configured_provider_catalog_model_ref(static_id)


__all__ = [
    "ManifestModelIdNormalizationProvider",
    "ManifestModelIdNormalizationRecord",
    "ModelIdNormalizationPolicies",
    "PrefixWhenBareAfterAliasRule",
    "collect_manifest_model_id_normalization_policies",
    "normalize_builtin_provider_model_id",
    "normalize_configured_provider_catalog_model_id",
    "normalize_configured_provider_catalog_model_ref",
    "normalize_provider_model_id_with_policies",
    "normalize_static_provider_model_id_with_policies",
    "set_current_manifest_model_id_normalization_policies",
    "strip_self_provider_model_prefix",
]
