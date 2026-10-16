"""Configuration schema and resolution for visitor-access."""

from __future__ import annotations

from typing import Any, TypedDict

from .errors import VisitorAccessError

DEFAULT_POLICY_NAME = "Visitors (openclaw-managed)"
DEFAULT_TTL_DAYS = 14
DEFAULT_MAX_VISITORS = 50


class VisitorAccessConfig(TypedDict):
    accountId: str
    appId: str
    apiToken: str
    policyName: str
    defaultTtlDays: int | None
    maxVisitors: int


def resolve_visitor_access_config(raw_config: Any) -> VisitorAccessConfig:
    if not isinstance(raw_config, dict):
        raise VisitorAccessError("visitor-access config must be a JSON object")

    account_id = str(raw_config.get("accountId") or "").strip()
    app_id = str(raw_config.get("appId") or "").strip()
    api_token = str(raw_config.get("apiToken") or "").strip()

    if not account_id:
        raise VisitorAccessError("visitor-access: accountId is required")
    if not app_id:
        raise VisitorAccessError("visitor-access: appId is required")
    if not api_token:
        raise VisitorAccessError("visitor-access: apiToken is required")

    policy_name = str(raw_config.get("policyName") or DEFAULT_POLICY_NAME).strip()

    default_ttl = raw_config.get("defaultTtlDays")
    if default_ttl is not None:
        try:
            default_ttl = max(0, min(3650, int(default_ttl)))
        except (ValueError, TypeError):
            default_ttl = DEFAULT_TTL_DAYS
    else:
        default_ttl = DEFAULT_TTL_DAYS

    max_visitors = raw_config.get("maxVisitors")
    if max_visitors is not None:
        try:
            max_visitors = max(1, min(500, int(max_visitors)))
        except (ValueError, TypeError):
            max_visitors = DEFAULT_MAX_VISITORS
    else:
        max_visitors = DEFAULT_MAX_VISITORS

    return {
        "accountId": account_id,
        "appId": app_id,
        "apiToken": api_token,
        "policyName": policy_name,
        "defaultTtlDays": default_ttl,
        "maxVisitors": max_visitors,
    }
