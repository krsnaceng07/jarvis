"""jarvis.config.runtime_group_policy — runtime group-policy resolver.

OpenClaw parity: mirrors
``openclaw-main/src/config/runtime-group-policy.ts``.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


def _create_dedupe_cache_stub():
    class _Stub:
        def check(self, _key):
            return False

        def add(self, _key):
            pass

    return _Stub()


#: Default warn-once key cap.
MAX_WARNED_MISSING_PROVIDER_GROUP_POLICY_KEYS = 4096
#: Per-provider warn-once dedupe cache (process-local).
_warned_missing_provider_group_policy = _create_dedupe_cache_stub()


def resolve_default_group_policy(cfg: Any) -> Optional[str]:
    """Read the shared channels default group policy used by provider-specific resolvers.

    Mirrors :func:`resolveDefaultGroupPolicy`
    (``shared/config/runtime-group-policy.ts`).
    """
    if not isinstance(cfg, dict):
        return None
    channels = cfg.get("channels")
    if not isinstance(channels, dict):
        return None
    defaults = channels.get("defaults")
    if not isinstance(defaults, dict):
        return None
    return defaults.get("groupPolicy")


#: Human labels for the access surface blocked by a missing-provider fallback.
GROUP_POLICY_BLOCKED_LABEL: dict = {
    "group": "group messages",
    "guild": "guild messages",
    "room": "room messages",
    "channel": "channel messages",
    "space": "space messages",
}


def _resolve_runtime_group_policy(params: dict) -> dict:
    """Internal: apply configured-vs-missing-provider fallback selection."""
    configured_fallback = params.get("configuredFallbackPolicy") or "open"
    missing_fallback = params.get("missingProviderFallbackPolicy") or "allowlist"
    provider_config_present = bool(params.get("providerConfigPresent"))
    explicit = params.get("groupPolicy")
    default = params.get("defaultGroupPolicy")
    if provider_config_present:
        group_policy = explicit if explicit is not None else (
            default if default is not None else configured_fallback
        )
    else:
        group_policy = explicit if explicit is not None else missing_fallback
    provider_missing_fallback_applied = (
        not provider_config_present and explicit is None
    )
    return {
        "groupPolicy": group_policy,
        "providerMissingFallbackApplied": provider_missing_fallback_applied,
    }


def resolve_open_provider_runtime_group_policy(params: dict) -> dict:
    """Resolve the standard channel-provider policy (missing defaults to allowlist).

    Mirrors :func:`resolveOpenProviderRuntimeGroupPolicy`
    (``shared/config/runtime-group-policy.ts`).
    """
    return _resolve_runtime_group_policy({
        "providerConfigPresent": bool(params.get("providerConfigPresent")),
        "groupPolicy": params.get("groupPolicy"),
        "defaultGroupPolicy": params.get("defaultGroupPolicy"),
        "configuredFallbackPolicy": "open",
        "missingProviderFallbackPolicy": "allowlist",
    })


def resolve_allowlist_provider_runtime_group_policy(params: dict) -> dict:
    """Resolve the strict channel-provider policy (always allowlist fallback).

    Mirrors :func:`resolveAllowlistProviderRuntimeGroupPolicy`
    (``shared/config/runtime-group-policy.ts`).
    """
    return _resolve_runtime_group_policy({
        "providerConfigPresent": bool(params.get("providerConfigPresent")),
        "groupPolicy": params.get("groupPolicy"),
        "defaultGroupPolicy": params.get("defaultGroupPolicy"),
        "configuredFallbackPolicy": "allowlist",
        "missingProviderFallbackPolicy": "allowlist",
    })


def warn_missing_provider_group_policy_fallback_once(
    params: dict,
    *,
    create_dedupe_cache_fn: Optional[Callable] = None,
) -> bool:
    """Log the missing-provider fail-closed fallback once per provider/account.

    Returns ``True`` only when this call emitted the warning.
    """
    if not params.get("providerMissingFallbackApplied"):
        return False
    provider_key = params.get("providerKey") or "?"
    account_id = params.get("accountId") or "*"
    log = params.get("log")
    blocked_label = params.get("blockedLabel") or "group messages"
    cache = _warned_missing_provider_group_policy
    if hasattr(cache, "check"):
        key = f"{provider_key}:{account_id}"
        if cache.check(key):
            return False
    if callable(log):
        log(
            f"{provider_key}: channels.{provider_key} is missing; defaulting "
            f'groupPolicy to "allowlist" ({blocked_label} blocked until explicitly configured).'
        )
    return True


__all__ = [
    "MAX_WARNED_MISSING_PROVIDER_GROUP_POLICY_KEYS",
    "GROUP_POLICY_BLOCKED_LABEL",
    "resolve_default_group_policy",
    "resolve_open_provider_runtime_group_policy",
    "resolve_allowlist_provider_runtime_group_policy",
    "warn_missing_provider_group_policy_fallback_once",
]
