"""jarvis.agents.embedded_agent_runner.cache_ttl — cache-TTL eligibility and session markers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/cache-ttl.ts``.

Public surface:

- :func:`is_cache_ttl_eligible_provider`
- :func:`read_last_cache_ttl_timestamp`

Phase 7.6h-3 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


CACHE_TTL_CUSTOM_TYPE = "openclaw.cache-ttl"

# Installable hooks ---------------------------------------------------------

_is_cache_ttl_eligible_provider_hook = None
_read_last_cache_ttl_timestamp_hook = None


def set_is_cache_ttl_eligible_provider_hook(fn) -> None:
    global _is_cache_ttl_eligible_provider_hook
    _is_cache_ttl_eligible_provider_hook = fn


def set_read_last_cache_ttl_timestamp_hook(fn) -> None:
    global _read_last_cache_ttl_timestamp_hook
    _read_last_cache_ttl_timestamp_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_cache_ttl_eligible_provider(
    provider: str,
    model_id: str,
    model_api: Optional[str] = None,
) -> bool:
    """Return whether this provider/model pair supports cache-TTL session markers.

    Mirrors :func:`isCacheTtlEligibleProvider` (``cache-ttl.ts``).
    """
    if _is_cache_ttl_eligible_provider_hook is not None:
        return bool(
            _is_cache_ttl_eligible_provider_hook(
                {"provider": provider, "modelId": model_id, "modelApi": model_api}
            )
        )
    # Default: anthropic family or google-generative-ai with gemini-2.5/3
    p = (provider or "").lower()
    m = (model_id or "").lower()
    if p == "anthropic":
        return True
    if p == "google" and (model_api or "") == "google-generative-ai":
        return m.startswith("gemini-2.5") or m.startswith("gemini-3")
    if p == "kilocode" and m.startswith("claude"):
        return True
    return False


def _normalize_cache_ttl_key(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip().lower()
    return v or None


def _matches_cache_ttl_context(
    data: Optional[Dict[str, Any]],
    context: Optional[Dict[str, Any]],
) -> bool:
    if not context:
        return True
    expected_provider = _normalize_cache_ttl_key(context.get("provider"))
    if expected_provider and _normalize_cache_ttl_key((data or {}).get("provider")) != expected_provider:
        return False
    expected_model_id = _normalize_cache_ttl_key(context.get("modelId"))
    if expected_model_id and _normalize_cache_ttl_key((data or {}).get("modelId")) != expected_model_id:
        return False
    return True


def read_last_cache_ttl_timestamp(
    session_manager: Any,
    context: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """Read the most recent cache-TTL marker that matches the optional provider/model context.

    Mirrors :func:`readLastCacheTtlTimestamp` (``cache-ttl.ts``).
    """
    if _read_last_cache_ttl_timestamp_hook is not None:
        v = _read_last_cache_ttl_timestamp_hook(
            {"sessionManager": session_manager, "context": context}
        )
        return int(v) if v is not None else None
    sm = session_manager if isinstance(session_manager, dict) else None
    get_entries = sm.get("getEntries") if sm else None
    if not callable(get_entries):
        return None
    try:
        entries = get_entries() or []
    except Exception:
        return None
    last: Optional[int] = None
    for entry in reversed(entries):
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != "custom" or entry.get("customType") != CACHE_TTL_CUSTOM_TYPE:
            continue
        data = entry.get("data") if isinstance(entry.get("data"), dict) else None
        if not _matches_cache_ttl_context(data, context):
            continue
        ts = data.get("timestamp") if data else None
        if isinstance(ts, (int, float)) and ts > 0:
            last = int(ts)
            break
    return last


__all__ = [
    "CACHE_TTL_CUSTOM_TYPE",
    "is_cache_ttl_eligible_provider",
    "read_last_cache_ttl_timestamp",
    "set_is_cache_ttl_eligible_provider_hook",
    "set_read_last_cache_ttl_timestamp_hook",
]
