"""jarvis.config.web_search_legacy_provider_keys — legacy web-search provider keys.

OpenClaw parity: mirrors
``openclaw-main/src/config/web-search-legacy-provider-keys.ts``.
"""
from __future__ import annotations


#: Legacy config keys that used to live under web-search provider config.
LEGACY_WEB_SEARCH_PROVIDER_CONFIG_KEYS = frozenset({
    "brave",
    "duckduckgo",
    "exa",
    "firecrawl",
    "gemini",
    "grok",
    "kimi",
    "minimax",
    "ollama",
    "perplexity",
    "searxng",
    "tavily",
})


def is_legacy_web_search_provider_config_key(key: str) -> bool:
    """Return whether ``key`` is a legacy web-search provider config key.

    Mirrors :func:`isLegacyWebSearchProviderConfigKey`
    (``shared/config/web-search-legacy-provider-keys.ts`).
    """
    return key in LEGACY_WEB_SEARCH_PROVIDER_CONFIG_KEYS


__all__ = [
    "LEGACY_WEB_SEARCH_PROVIDER_CONFIG_KEYS",
    "is_legacy_web_search_provider_config_key",
]
