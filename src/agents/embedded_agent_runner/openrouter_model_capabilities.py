"""jarvis.agents.embedded_agent_runner.openrouter_model_capabilities — runtime OpenRouter capabilities.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/openrouter-model-capabilities.ts``.

Public surface:

- :func:`load_open_router_model_capabilities`
- :func:`get_open_router_model_capabilities`

Phase 7.6h-4 — focused minimal port.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional


_log = logging.getLogger("jarvis.openrouter_model_capabilities")

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
FETCH_TIMEOUT_MS = 10_000
OPENROUTER_MODELS_RESPONSE_MAX_BYTES = 16 * 1024 * 1024
SQLITE_CACHE_OWNER_ID = "core:openrouter-model-capabilities"
SQLITE_CACHE_NAMESPACE = "models.v3"
SQLITE_CACHE_MAX_ENTRIES = 10_000

#: Process-local cache.
_cache: Optional[Dict[str, Dict[str, Any]]] = None
_fetch_in_flight: Optional[Any] = None
_skip_next_miss_refresh: set = set()


# Installable hooks ---------------------------------------------------------

_load_open_router_model_capabilities_hook = None
_get_open_router_model_capabilities_hook = None


def set_load_open_router_model_capabilities_hook(fn) -> None:
    global _load_open_router_model_capabilities_hook
    _load_open_router_model_capabilities_hook = fn


def set_get_open_router_model_capabilities_hook(fn) -> None:
    global _get_open_router_model_capabilities_hook
    _get_open_router_model_capabilities_hook = fn


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _is_valid_capabilities(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        isinstance(value.get("name"), str)
        and isinstance(value.get("input"), list)
        and isinstance(value.get("reasoning"), bool)
        and isinstance(value.get("contextWindow"), (int, float))
        and isinstance(value.get("maxTokens"), (int, float))
    )


def _parse_model(model: Dict[str, Any]) -> Dict[str, Any]:
    arch = model.get("architecture") or {}
    if not isinstance(arch, dict):
        arch = {}
    modality = arch.get("modality") or model.get("modality") or ""
    input_modes = ["text"]
    if isinstance(modality, str) and "image" in (modality.split("->")[0] if "->" in modality else modality):
        input_modes.append("image")
    supported = model.get("supported_parameters")
    has_tools = False
    has_reasoning = False
    if isinstance(supported, list):
        has_tools = "tools" in supported
        has_reasoning = "reasoning" in supported

    top_provider = model.get("top_provider") or {}
    if not isinstance(top_provider, dict):
        top_provider = {}
    pricing = model.get("pricing") or {}
    if not isinstance(pricing, dict):
        pricing = {}

    def _num(v: Any, default: float) -> float:
        try:
            f = float(v)
            if f != f or f in (float("inf"), float("-inf")):
                return default
            return f
        except (TypeError, ValueError):
            return default

    out: Dict[str, Any] = {
        "name": model.get("name") or model.get("id") or "",
        "input": input_modes,
        "reasoning": has_reasoning,
        "contextWindow": int(_num(top_provider.get("context_length"), _num(model.get("context_length"), 128_000))),
        "maxTokens": int(_num(
            top_provider.get("max_completion_tokens"),
            _num(model.get("max_completion_tokens"), _num(model.get("max_output_tokens"), 8192)),
        )),
        "cost": {
            "input": _num(pricing.get("prompt"), 0) * 1_000_000,
            "output": _num(pricing.get("completion"), 0) * 1_000_000,
            "cacheRead": _num(pricing.get("input_cache_read"), 0) * 1_000_000,
            "cacheWrite": _num(pricing.get("input_cache_write"), 0) * 1_000_000,
        },
    }
    if has_tools:
        out["supportsTools"] = True
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def load_open_router_model_capabilities(model_id: str) -> None:
    """Ensure capabilities for a specific model are available before first use.

    Mirrors :func:`loadOpenRouterModelCapabilities`
    (``openrouter-model-capabilities.ts``).
    """
    if _load_open_router_model_capabilities_hook is not None:
        v = _load_open_router_model_capabilities_hook(model_id)
        if hasattr(v, "__await__"):
            await v  # type: ignore[func-returns-value]
        return
    if _cache is not None and model_id in _cache:
        return
    # The full network + SQLite cache lives in the
    # `jarvis.agents.embedded_agent_runner.openrouter_model_capabilities.runtime`
    # module; the focused port just touches the in-memory map. Tests that
    # exercise the cache should pre-seed it.
    return


def get_open_router_model_capabilities(model_id: str) -> Optional[Dict[str, Any]]:
    """Look up the cached OpenRouter model capabilities for a given id.

    Mirrors :func:`getOpenRouterModelCapabilities`
    (``openrouter-model-capabilities.ts``).
    """
    if _get_open_router_model_capabilities_hook is not None:
        v = _get_open_router_model_capabilities_hook(model_id)
        return v if v is None or isinstance(v, dict) else None
    if _cache is None:
        return None
    if model_id in _skip_next_miss_refresh:
        _skip_next_miss_refresh.discard(model_id)
    return _cache.get(model_id)


def _seed_cache_for_testing(capabilities: Dict[str, Dict[str, Any]]) -> None:
    """Test helper: replace the in-memory cache with a synthetic map."""
    global _cache
    cleaned: Dict[str, Dict[str, Any]] = {}
    for model_id, caps in capabilities.items():
        if _is_valid_capabilities(caps):
            cleaned[model_id] = caps
    _cache = cleaned or None


def _reset_cache_for_testing() -> None:
    """Test helper: clear the in-memory cache."""
    global _cache
    _cache = None
    _skip_next_miss_refresh.clear()


__all__ = [
    "OPENROUTER_MODELS_URL",
    "FETCH_TIMEOUT_MS",
    "OPENROUTER_MODELS_RESPONSE_MAX_BYTES",
    "SQLITE_CACHE_OWNER_ID",
    "SQLITE_CACHE_NAMESPACE",
    "SQLITE_CACHE_MAX_ENTRIES",
    "load_open_router_model_capabilities",
    "get_open_router_model_capabilities",
    "set_load_open_router_model_capabilities_hook",
    "set_get_open_router_model_capabilities_hook",
]
