"""jarvis.plugins.provider_thinking — provider thinking-level policy.

OpenClaw parity: mirrors
``openclaw-main/src/plugins/provider-thinking.ts``.

Resolves provider thinking-level policy from active plugins or plugin
metadata.

Adaptations
-----------
- The OpenClaw source's public-artifact fallback
  (``resolveProviderPublicPolicySurface`` →
  ``getCurrentPluginMetadataSnapshot`` +
  ``resolveProviderPolicySurface``) reads the bundled provider policy
  surface from the plugin manifest registry. That registry projection
  has no Python port yet; the port exposes the same seam via a
  module-level hook
  (:func:`set_resolve_provider_public_policy_surface_hook`) that
  defaults to ``None`` (no bundled surface). The active-registry path
  is fully ported.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from .provider_thinking_active import (
    resolve_active_provider_binary_thinking,
    resolve_active_provider_default_thinking_level,
    resolve_active_provider_thinking_profile,
    resolve_active_provider_xhigh_thinking,
)

#: The bundled policy-surface hook. Mirrors
#: ``resolveProviderPublicPolicySurface``
#: (``provider-thinking.ts:15-23``); returns an object/dict with an
#: optional ``resolveThinkingProfile`` callable, or ``None``.
_resolve_provider_public_policy_surface_hook: Optional[
    Callable[[str], Any]
] = None


def set_resolve_provider_public_policy_surface_hook(
    hook: Optional[Callable[[str], Any]],
) -> None:
    """Install/clear the bundled policy-surface hook (adaptation seam)."""
    global _resolve_provider_public_policy_surface_hook
    _resolve_provider_public_policy_surface_hook = hook


def _normalize_provider_id(provider_id: Any) -> str:
    return provider_id.strip().lower() if isinstance(provider_id, str) else ""


def _bundled_openai_thinking_surface() -> dict[str, Any]:
    """Owner-side OpenAI thinking surface (cold artifact, no runtime load).

    Mirrors ``resolveDirectBundledProviderPolicySurface("openai")`` for the
    thinking surface: the ``extensions/openai`` owner module exposes
    ``resolve_thinking_profile``; core calls it without loading provider
    runtime. Same lazy pattern as ``src/agents/openai_model_routes.py``.
    """
    from extensions.openai.thinking_policy import (  # noqa: PLC0415
        resolve_thinking_profile,
    )

    return {"resolveThinkingProfile": resolve_thinking_profile}


def _resolve_provider_public_policy_surface(provider_id: str) -> Any:
    """Mirrors ``resolveProviderPublicPolicySurface``
    (``provider-thinking.ts:15-23``) via the installed hook, falling back
    to the bundled OpenAI owner surface (the only bundled thinking
    surface ported so far)."""
    if _resolve_provider_public_policy_surface_hook is not None:
        return _resolve_provider_public_policy_surface_hook(provider_id)
    if _normalize_provider_id(provider_id) == "openai":
        try:
            return _bundled_openai_thinking_surface()
        except ImportError:
            return None
    return None


def resolve_provider_binary_thinking(params: dict) -> Any:
    """Resolves whether a provider treats thinking as binary on/off.
    Mirrors ``resolveProviderBinaryThinking``
    (``provider-thinking.ts:31-35``)."""
    return resolve_active_provider_binary_thinking(params)


def resolve_provider_xhigh_thinking(params: dict) -> Any:
    """Resolves whether a provider supports xhigh thinking. Mirrors
    ``resolveProviderXHighThinking``
    (``provider-thinking.ts:38-42``)."""
    return resolve_active_provider_xhigh_thinking(params)


def resolve_provider_thinking_profile(
    params: dict,
    options: Optional[dict] = None,
) -> Any:
    """Resolves a provider thinking profile from active plugins or the
    bundled policy surface. Mirrors
    ``resolveProviderThinkingProfile``
    (``provider-thinking.ts:45-59``)."""
    active_profile = resolve_active_provider_thinking_profile(params)
    if active_profile is not None:
        return active_profile
    if options and options.get("allowPublicArtifactFallback") is False:
        return None
    surface = _resolve_provider_public_policy_surface(
        params.get("provider", "")
    )
    if surface is None:
        return None
    resolve = (
        surface.get("resolveThinkingProfile")
        if isinstance(surface, dict)
        else getattr(surface, "resolve_thinking_profile", None)
    )
    if not callable(resolve):
        return None
    return resolve(params.get("context"))


def resolve_provider_default_thinking_level(params: dict) -> Any:
    """Resolves the provider default thinking level from the active
    plugin registry. Mirrors
    ``resolveProviderDefaultThinkingLevel``
    (``provider-thinking.ts:62-66``)."""
    return resolve_active_provider_default_thinking_level(params)


def resolve_host_thinking_policy(params: dict) -> dict[str, Any]:
    """Resolve the host thinking policy for a (provider, model) pair.

    Host-side default for ``api.runtime.agent.resolve_thinking_policy``:
    accepts the llm-task call shape ``{"provider", "model",
    "agentRuntime", "catalog"?, "api"?, "compat"?}`` and returns
    ``{"levels": [{"id", "label"}], "default"?}``. Active-registry
    profiles win; otherwise the bundled owner surface answers (today:
    OpenAI). An empty profile keeps the levels list empty so callers
    fall back to their local heuristics.
    """
    if not isinstance(params, dict):
        return {"levels": []}
    provider = params.get("provider")
    context: dict[str, Any] = {
        "provider": provider,
        "modelId": params.get("model"),
        "agentRuntime": params.get("agentRuntime"),
    }
    for key in ("compat", "api", "catalog"):
        if params.get(key) is not None:
            context[key] = params[key]
    profile = resolve_provider_thinking_profile({"provider": provider, "context": context})
    if not isinstance(profile, dict):
        return {"levels": []}
    levels: list[dict[str, str]] = []
    raw_levels = profile.get("levels")
    if isinstance(raw_levels, list):
        for entry in raw_levels:
            level_id = entry.get("id") if isinstance(entry, dict) else entry
            if isinstance(level_id, str) and level_id.strip():
                levels.append({"id": level_id.strip(), "label": level_id.strip()})
    resolved: dict[str, Any] = {"levels": levels}
    default = profile.get("defaultLevel", profile.get("default"))
    if isinstance(default, str) and default.strip():
        resolved["default"] = default.strip()
    return resolved


__all__ = [
    "resolve_host_thinking_policy",
    "resolve_provider_binary_thinking",
    "resolve_provider_default_thinking_level",
    "resolve_provider_thinking_profile",
    "resolve_provider_xhigh_thinking",
    "set_resolve_provider_public_policy_surface_hook",
]
