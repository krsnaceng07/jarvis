"""jarvis.config.dangerous_name_matching — dangerous name matching flag resolver.

OpenClaw parity: mirrors ``openclaw-main/src/config/dangerous-name-matching.ts``.
"""
from __future__ import annotations

from typing import Any, List, TypedDict


class ProviderDangerousNameMatchingScope(TypedDict, total=False):
    prefix: str
    account: dict
    dangerousNameMatchingEnabled: bool
    dangerousFlagPath: str


def _as_object_record(value) -> dict:
    if not value or not isinstance(value, dict) or isinstance(value, list):
        return {}
    return value


def _as_boolean(value) -> bool:
    """Coerce a value to a boolean. Returns False for None."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return bool(value)


def is_dangerous_name_matching_enabled(config) -> bool:
    """Return true only for the explicit dangerous name-matching opt-in flag.

    Mirrors :func:`isDangerousNameMatchingEnabled`
    (``shared/config/dangerous-name-matching.ts``).
    """
    if not isinstance(config, dict):
        return False
    return config.get("dangerouslyAllowNameMatching") is True


def resolve_dangerous_name_matching_enabled(input_: dict) -> bool:
    """Resolve account-level dangerous name matching, inheriting provider flag.

    Mirrors :func:`resolveDangerousNameMatchingEnabled`
    (``shared/config/dangerous-name-matching.ts``).
    """
    account = input_.get("accountConfig")
    if isinstance(account, dict) and "dangerouslyAllowNameMatching" in account:
        return _as_boolean(account.get("dangerouslyAllowNameMatching"))
    return is_dangerous_name_matching_enabled(input_.get("providerConfig"))


def collect_provider_dangerous_name_matching_scopes(
    cfg: Any, provider: str
) -> List[ProviderDangerousNameMatchingScope]:
    """Collect provider/account scopes that policy surfaces can audit.

    Mirrors :func:`collectProviderDangerousNameMatchingScopes`
    (``shared/config/dangerous-name-matching.ts``).
    """
    scopes: List[ProviderDangerousNameMatchingScope] = []
    channels = _as_object_record(cfg.get("channels") if isinstance(cfg, dict) else None)
    if not channels:
        return scopes
    provider_cfg = _as_object_record(channels.get(provider))
    if not provider_cfg:
        return scopes
    provider_prefix = f"channels.{provider}"
    provider_dangerous_flag_path = f"{provider_prefix}.dangerouslyAllowNameMatching"
    provider_dangerous_enabled = is_dangerous_name_matching_enabled(provider_cfg)
    scopes.append({
        "prefix": provider_prefix,
        "account": provider_cfg,
        "dangerousNameMatchingEnabled": provider_dangerous_enabled,
        "dangerousFlagPath": provider_dangerous_flag_path,
    })
    accounts = _as_object_record(provider_cfg.get("accounts"))
    if not accounts:
        return scopes
    for key in accounts.keys():
        account = _as_object_record(accounts[key])
        if not account:
            continue
        account_prefix = f"{provider_prefix}.accounts.{key}"
        account_value = account.get("dangerouslyAllowNameMatching")
        scopes.append({
            "prefix": account_prefix,
            "account": account,
            "dangerousNameMatchingEnabled": (
                _as_boolean(account_value)
                if "dangerouslyAllowNameMatching" in account
                else provider_dangerous_enabled
            ),
            "dangerousFlagPath": (
                provider_dangerous_flag_path
                if account_value is None
                else f"{account_prefix}.dangerouslyAllowNameMatching"
            ),
        })
    return scopes


__all__ = [
    "ProviderDangerousNameMatchingScope",
    "is_dangerous_name_matching_enabled",
    "resolve_dangerous_name_matching_enabled",
    "collect_provider_dangerous_name_matching_scopes",
]
