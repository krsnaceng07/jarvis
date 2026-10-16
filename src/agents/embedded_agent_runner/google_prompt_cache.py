"""jarvis.agents.embedded_agent_runner.google_prompt_cache — Google prompt-cache payload preparation.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/google-prompt-cache.ts``.

Public surface:

- :func:`prepare_google_prompt_cache_stream_fn`
- :func:`read_latest_google_prompt_cache_entry`
- :func:`build_google_prompt_cache_match_key`
- :data:`GOOGLE_PROMPT_CACHE_CUSTOM_TYPE`
- :data:`GOOGLE_PROMPT_CACHE_RETRY_BACKOFF_MS`
- :data:`GOOGLE_PROMPT_CACHE_SHORT_REFRESH_WINDOW_MS`
- :data:`GOOGLE_PROMPT_CACHE_LONG_REFRESH_WINDOW_MS`

Phase 7.6h-5 — focused minimal port.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, Optional


_log = logging.getLogger("jarvis.agents.embedded_agent_runner.google_prompt_cache")

GOOGLE_PROMPT_CACHE_CUSTOM_TYPE = "openclaw.google-prompt-cache"
GOOGLE_PROMPT_CACHE_RESPONSE_MAX_BYTES = 1024 * 1024
GOOGLE_PROMPT_CACHE_RETRY_BACKOFF_MS = 10 * 60_000
GOOGLE_PROMPT_CACHE_SHORT_REFRESH_WINDOW_MS = 30_000
GOOGLE_PROMPT_CACHE_LONG_REFRESH_WINDOW_MS = 5 * 60_000


# Installable hooks ---------------------------------------------------------

_prepare_google_prompt_cache_stream_fn_hook = None
_read_latest_google_prompt_cache_entry_hook = None
_build_google_prompt_cache_match_key_hook = None


def set_prepare_google_prompt_cache_stream_fn_hook(fn) -> None:
    global _prepare_google_prompt_cache_stream_fn_hook
    _prepare_google_prompt_cache_stream_fn_hook = fn


def set_read_latest_google_prompt_cache_entry_hook(fn) -> None:
    global _read_latest_google_prompt_cache_entry_hook
    _read_latest_google_prompt_cache_entry_hook = fn


def set_build_google_prompt_cache_match_key_hook(fn) -> None:
    global _build_google_prompt_cache_match_key_hook
    _build_google_prompt_cache_match_key_hook = fn


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _stable_stringify(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest_system_prompt(system_prompt: str) -> str:
    return hashlib.sha256((system_prompt or "").encode("utf-8")).hexdigest()


def _resolve_google_prompt_cache_ttl(cache_retention: str) -> str:
    return "3600s" if cache_retention == "long" else "300s"


def _resolve_google_prompt_cache_refresh_window_ms(cache_retention: str) -> int:
    return (
        GOOGLE_PROMPT_CACHE_LONG_REFRESH_WINDOW_MS
        if cache_retention == "long"
        else GOOGLE_PROMPT_CACHE_SHORT_REFRESH_WINDOW_MS
    )


def _stringify_key_part(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_google_prompt_cache_match_key(params: Dict[str, Any]) -> str:
    """Build the stable match key for a Google prompt-cache entry.

    Mirrors :func:`buildGooglePromptCacheMatchKey` (``google-prompt-cache.ts``).
    """
    if _build_google_prompt_cache_match_key_hook is not None:
        return _build_google_prompt_cache_match_key_hook(params) or ""
    payload = {
        "provider": _stringify_key_part(params.get("provider")),
        "modelId": _stringify_key_part(params.get("modelId")),
        "modelApi": params.get("modelApi") if isinstance(params.get("modelApi"), str) else None,
        "baseUrl": _stringify_key_part(params.get("baseUrl")),
        "systemPromptDigest": _stringify_key_part(params.get("systemPromptDigest")),
        "cacheConfigDigest": params.get("cacheConfigDigest")
        if isinstance(params.get("cacheConfigDigest"), str)
        else None,
    }
    return _stable_stringify(payload)


def read_latest_google_prompt_cache_entry(
    session_manager: Any, match_key: str
) -> Optional[Dict[str, Any]]:
    """Read the most recent Google prompt-cache entry that matches ``match_key``.

    Mirrors :func:`readLatestGooglePromptCacheEntry` (``google-prompt-cache.ts``).
    """
    if _read_latest_google_prompt_cache_entry_hook is not None:
        v = _read_latest_google_prompt_cache_entry_hook(session_manager, match_key)
        return v if v is None or isinstance(v, dict) else None
    sm = session_manager if isinstance(session_manager, dict) else None
    get_entries = sm.get("getEntries") if sm else None
    if not callable(get_entries):
        return None
    try:
        entries = get_entries() or []
    except Exception:
        return None
    for entry in reversed(entries):
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != "custom" or entry.get("customType") != GOOGLE_PROMPT_CACHE_CUSTOM_TYPE:
            continue
        data = entry.get("data")
        if not isinstance(data, dict):
            continue
        candidate_key = build_google_prompt_cache_match_key(
            {
                "provider": data.get("provider"),
                "modelId": data.get("modelId"),
                "modelApi": data.get("modelApi"),
                "baseUrl": data.get("baseUrl"),
                "systemPromptDigest": data.get("systemPromptDigest"),
                "cacheConfigDigest": data.get("cacheConfigDigest"),
            }
        )
        if candidate_key == match_key:
            return data
    return None


def prepare_google_prompt_cache_stream_fn(
    params: Dict[str, Any],
) -> Any:
    """Wrap the embedded-agent stream function with Google prompt-cache preparation.

    Mirrors :func:`prepareGooglePromptCacheStreamFn` (``google-prompt-cache.ts``).
    """
    if _prepare_google_prompt_cache_stream_fn_hook is not None:
        return _prepare_google_prompt_cache_stream_fn_hook(params)
    # The default returns the original stream function unchanged; the heavy
    # CachedContent create / refresh logic is delegated to installable runtime
    # hooks.
    return params.get("streamFn")


def resolve_google_prompt_cache_ttl(cache_retention: str) -> str:
    return _resolve_google_prompt_cache_ttl(cache_retention)


def resolve_google_prompt_cache_refresh_window_ms(cache_retention: str) -> int:
    return _resolve_google_prompt_cache_refresh_window_ms(cache_retention)


__all__ = [
    "GOOGLE_PROMPT_CACHE_CUSTOM_TYPE",
    "GOOGLE_PROMPT_CACHE_RESPONSE_MAX_BYTES",
    "GOOGLE_PROMPT_CACHE_RETRY_BACKOFF_MS",
    "GOOGLE_PROMPT_CACHE_SHORT_REFRESH_WINDOW_MS",
    "GOOGLE_PROMPT_CACHE_LONG_REFRESH_WINDOW_MS",
    "build_google_prompt_cache_match_key",
    "read_latest_google_prompt_cache_entry",
    "prepare_google_prompt_cache_stream_fn",
    "resolve_google_prompt_cache_ttl",
    "resolve_google_prompt_cache_refresh_window_ms",
    "set_prepare_google_prompt_cache_stream_fn_hook",
    "set_read_latest_google_prompt_cache_entry_hook",
    "set_build_google_prompt_cache_match_key_hook",
]
