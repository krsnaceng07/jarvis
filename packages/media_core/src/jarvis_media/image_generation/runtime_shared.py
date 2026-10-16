"""
Shared capabilities and fallback resolution logic.
"""

from typing import Any, Callable, Optional


def resolve_capability_model_candidates(
    cfg: Any,
    model_config: Any,
    model_override: Optional[str],
    parse_model_ref: Callable[[Optional[str]], Optional[dict[str, str]]],
    agent_dir: Optional[str],
    list_providers: Callable[[], list[Any]],
    auto_provider_fallback: Optional[bool] = None,
) -> list[dict[str, str]]:
    """
    Resolve which provider/model combinations to try, in order of preference.
    """
    candidates: list[dict[str, str]] = []

    # 1. Override model if provided
    if model_override:
        ref = parse_model_ref(model_override)
        if ref:
            candidates.append(ref)
            # If explicit model given, we don't fallback unless requested
            if not auto_provider_fallback:
                return candidates
        else:
            # Maybe it's just a provider name, or just a model name?
            # OpenClaw has more complex fallback, but simple for now
            pass

    # 2. Configured primary model
    if model_config and getattr(model_config, "primary", None):
        ref = parse_model_ref(model_config.primary)
        if ref and ref not in candidates:
            candidates.append(ref)

    # 3. Configured fallbacks
    if model_config and getattr(model_config, "fallbacks", None):
        for fallback in model_config.fallbacks:
            ref = parse_model_ref(fallback)
            if ref and ref not in candidates:
                candidates.append(ref)

    # 4. If auto_provider_fallback is enabled (or explicit override wasn't used),
    # add all default models of available providers.
    if auto_provider_fallback is not False:
        for provider in list_providers():
            if provider.default_model:
                ref = {"provider": provider.id, "model": provider.default_model}
                if ref not in candidates:
                    candidates.append(ref)

    return candidates


def build_media_generation_normalization_metadata(
    normalization: Optional[Any],
    requested_size_for_derived_aspect_ratio: Optional[str] = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if not normalization:
        return metadata

    if normalization.size and normalization.size.applied is not None:
        metadata["requestedSize"] = getattr(normalization.size, "requested", None)
        metadata["normalizedSize"] = normalization.size.applied

    if normalization.aspect_ratio and normalization.aspect_ratio.applied is not None:
        metadata["requestedAspectRatio"] = getattr(normalization.aspect_ratio, "requested", None)
        metadata["normalizedAspectRatio"] = normalization.aspect_ratio.applied
        if (
            normalization.aspect_ratio.derived_from == "size"
            and requested_size_for_derived_aspect_ratio
        ):
            metadata["requestedSize"] = requested_size_for_derived_aspect_ratio
            # OpenClaw derives it here; we just record it.

    if normalization.resolution and normalization.resolution.applied is not None:
        metadata["requestedResolution"] = getattr(normalization.resolution, "requested", None)
        metadata["normalizedResolution"] = normalization.resolution.applied

    return metadata


def build_no_capability_model_configured_message(
    capability_label: str,
    model_config_key: str,
    providers: list[Any],
) -> str:
    sample = None
    for p in providers:
        if p.id and p.default_model:
            sample = f"{p.id}/{p.default_model}"
            break

    ref = sample or "<provider>/<model>"
    return (
        f"No {capability_label} model configured. "
        f"Set agents.defaults.{model_config_key}.primary to a provider/model like '{ref}'."
    )
