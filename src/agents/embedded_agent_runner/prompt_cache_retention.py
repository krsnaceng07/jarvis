"""jarvis.agents.embedded_agent_runner.prompt_cache_retention — provider/model prompt-cache retention.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/prompt-cache-retention.ts``.

Public surface:

- :func:`parse_cache_retention`
- :func:`is_google_prompt_cache_eligible`
- :func:`resolve_cache_retention`

Phase 7.6h-3 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


CacheRetention = str  # "none" | "short" | "long"


# Installable hooks ---------------------------------------------------------

_resolve_cache_retention_hook = None


def set_resolve_cache_retention_hook(fn) -> None:
    global _resolve_cache_retention_hook
    _resolve_cache_retention_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_cache_retention(value: Any) -> Optional[CacheRetention]:
    """Parse a raw value into one of the three cache-retention levels.

    Mirrors :func:`parseCacheRetention` (``prompt-cache-retention.ts``).
    """
    if value in ("none", "short", "long"):
        return value  # type: ignore[return-value]
    return None


def is_google_prompt_cache_eligible(params: Dict[str, Any]) -> bool:
    """Return whether a model is Google prompt-cache eligible.

    Mirrors :func:`isGooglePromptCacheEligible` (``prompt-cache-retention.ts``).
    """
    if (params.get("modelApi") or "") != "google-generative-ai":
        return False
    model_id = (params.get("modelId") or "").lower()
    return model_id.startswith("gemini-2.5") or model_id.startswith("gemini-3")


def resolve_cache_retention(
    extra_params: Optional[Dict[str, Any]],
    provider: str,
    model_api: Optional[str] = None,
    model_id: Optional[str] = None,
    supports_prompt_cache_key: Optional[bool] = None,
) -> Optional[CacheRetention]:
    """Resolve the cache-retention value for a model and its extra params.

    Mirrors :func:`resolveCacheRetention` (``prompt-cache-retention.ts``).
    """
    if _resolve_cache_retention_hook is not None:
        v = _resolve_cache_retention_hook(
            {
                "extraParams": extra_params,
                "provider": provider,
                "modelApi": model_api,
                "modelId": model_id,
                "supportsPromptCacheKey": supports_prompt_cache_key,
            }
        )
        return v if v is None else str(v)
    p = (provider or "").lower()
    api = model_api or ""
    mid = (model_id or "").lower()
    extra = extra_params or {}
    has_explicit_cache_config = (
        extra.get("cacheRetention") is not None
        or extra.get("cacheControlTtl") is not None
    )
    is_anthropic = p == "anthropic"
    google_eligible = is_google_prompt_cache_eligible({"modelApi": api, "modelId": mid})
    cache_key_eligible = supports_prompt_cache_key is True

    if not is_anthropic and not google_eligible and not cache_key_eligible:
        return None

    explicit = parse_cache_retention(extra.get("cacheRetention"))
    if explicit:
        return explicit

    legacy = extra.get("cacheControlTtl")
    if legacy == "5m" and (is_anthropic or google_eligible):
        return "short"
    if legacy == "1h" and (is_anthropic or google_eligible):
        return "long"

    return "short" if is_anthropic and not has_explicit_cache_config else None


__all__ = [
    "parse_cache_retention",
    "is_google_prompt_cache_eligible",
    "resolve_cache_retention",
    "set_resolve_cache_retention_hook",
]
