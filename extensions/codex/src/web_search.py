"""OpenClaw-aligned native versus managed web-search planning."""

from __future__ import annotations

from typing import Any

_DISABLED_THREAD_CONFIG = {
    "features.standalone_web_search": False,
    "web_search": "disabled",
}


def build_codex_native_web_search_thread_config(config: dict[str, Any] | None) -> dict[str, Any]:
    search = ((config or {}).get("tools") or {}).get("web", {}).get("search", {})
    native = search.get("openaiCodex") or {}
    result: dict[str, Any] = {
        "features.standalone_web_search": False,
        "web_search": "live" if native.get("mode") == "live" else "cached",
    }
    domains = _unique_strings(native.get("allowedDomains"))
    if domains:
        result["tools.web_search.allowed_domains"] = domains
    if native.get("contextSize"):
        result["tools.web_search.context_size"] = native["contextSize"]
    location = native.get("userLocation") or {}
    for source, target in (
        ("country", "country"),
        ("region", "region"),
        ("city", "city"),
        ("timezone", "timezone"),
    ):
        value = location.get(source)
        if isinstance(value, str) and value.strip():
            result[f"tools.web_search.location.{target}"] = value.strip()
    return result


def resolve_codex_web_search_plan(
    config: dict[str, Any] | None = None,
    *,
    disable_tools: bool = False,
    native_tool_surface_enabled: bool = True,
    native_provider_support: str = "supported",
    web_search_allowed: bool = True,
) -> dict[str, Any]:
    """Choose exactly one search owner and prevent domain-policy bypass."""
    search = ((config or {}).get("tools") or {}).get("web", {}).get("search", {})
    native = search.get("openaiCodex") or {}
    managed_provider = search.get("provider")
    domains = _unique_strings(native.get("allowedDomains"))
    if disable_tools or not web_search_allowed or search.get("enabled") is False:
        return {
            "kind": "disabled",
            "suppressManagedWebSearch": True,
            "threadConfig": dict(_DISABLED_THREAD_CONFIG),
        }
    managed_explicit = isinstance(managed_provider, str) and bool(managed_provider.strip())
    native_enabled = (
        native_tool_surface_enabled
        and native_provider_support in ("supported",)
        and native.get("enabled") is not False
        and not managed_explicit
    )
    if not native_enabled:
        if not managed_explicit and domains:
            return {
                "kind": "disabled",
                "suppressManagedWebSearch": True,
                "threadConfig": dict(_DISABLED_THREAD_CONFIG),
            }
        return {
            "kind": "managed",
            "suppressManagedWebSearch": False,
            "threadConfig": dict(_DISABLED_THREAD_CONFIG),
        }
    return {
        "kind": "native-hosted",
        "suppressManagedWebSearch": True,
        "threadConfig": build_codex_native_web_search_thread_config(config),
        "webFetchHostnameAllowlist": domains,
    }


def _unique_strings(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    result = list(
        dict.fromkeys(item.strip() for item in value if isinstance(item, str) and item.strip())
    )
    return result or None


__all__ = [
    "build_codex_native_web_search_thread_config",
    "resolve_codex_web_search_plan",
]
