"""jarvis.config.zod_schema_secret_input_validation — webhook secret requirements.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.secret-input-validation.ts``.
"""
from __future__ import annotations

from typing import Any, List, Optional


def normalize_optional_string(value: Any) -> str:
    """Best-effort non-throwing trim."""
    if not isinstance(value, str):
        return ""
    return value.strip()


def has_configured_secret_input(value: Any) -> bool:
    """Return whether ``value`` is a non-empty SecretInput (string or object)."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value)
    return False


def _for_each_enabled_account(accounts, run) -> None:
    if not isinstance(accounts, dict):
        return
    for account_id, account in accounts.items():
        if not isinstance(account, dict) or account.get("enabled") is False:
            continue
        run(account_id, account)


def collect_telegram_webhook_secret_issues(value: Any) -> List[dict]:
    """Collect issues for the Telegram webhook secret requirement rule.

    Mirrors :func:`validateTelegramWebhookSecretRequirements`
    (``shared/config/zod-schema.secret-input-validation.ts`).
    """
    if not isinstance(value, dict):
        return []
    issues: List[dict] = []
    base_url = normalize_optional_string(value.get("webhookUrl"))
    base_secret_present = has_configured_secret_input(value.get("webhookSecret"))
    if base_url and not base_secret_present:
        issues.append({
            "path": ["webhookSecret"],
            "message": "channels.telegram.webhookUrl requires channels.telegram.webhookSecret",
        })
    accounts = value.get("accounts")
    _for_each_enabled_account(accounts, lambda account_id, account: (
        _check_account_webhook(issues, account_id, account, base_secret_present)
    ))
    return issues


def _check_account_webhook(issues, account_id, account, base_secret_present) -> None:
    account_url = normalize_optional_string(account.get("webhookUrl"))
    if not account_url:
        return
    account_secret_present = has_configured_secret_input(account.get("webhookSecret"))
    if account_secret_present or base_secret_present:
        return
    issues.append({
        "path": ["accounts", account_id, "webhookSecret"],
        "message": (
            "channels.telegram.accounts.*.webhookUrl requires "
            "channels.telegram.webhookSecret or "
            "channels.telegram.accounts.*.webhookSecret"
        ),
    })


def collect_slack_signing_secret_issues(value: Any) -> List[dict]:
    """Collect issues for the Slack signing-secret requirement rule.

    Mirrors :func:`validateSlackSigningSecretRequirements`
    (``shared/config/zod-schema.secret-input-validation.ts`).
    """
    if not isinstance(value, dict):
        return []

    def _resolve_mode(mode) -> Optional[str]:
        return mode if mode in ("http", "socket", "relay") else None

    issues: List[dict] = []
    base_mode = _resolve_mode(value.get("mode")) or "socket"
    base_secret_present = has_configured_secret_input(value.get("signingSecret"))
    if base_mode == "http" and not base_secret_present:
        issues.append({
            "path": ["signingSecret"],
            "message": 'channels.slack.mode="http" requires channels.slack.signingSecret',
        })
    accounts = value.get("accounts")
    _for_each_enabled_account(accounts, lambda account_id, account: (
        _check_account_slack_signing(issues, account_id, account, base_mode, base_secret_present)
    ))
    return issues


def _check_account_slack_signing(issues, account_id, account, base_mode, base_secret_present) -> None:
    def _resolve_mode(mode):
        return mode if mode in ("http", "socket", "relay") else None
    account_mode = _resolve_mode(account.get("mode")) or base_mode
    if account_mode != "http":
        return
    secret = account.get("signingSecret")
    if secret is None:
        secret_present = base_secret_present
    else:
        secret_present = has_configured_secret_input(secret)
    if secret_present:
        return
    issues.append({
        "path": ["accounts", account_id, "signingSecret"],
        "message": (
            'channels.slack.accounts.*.mode="http" requires '
            "channels.slack.signingSecret or "
            'channels.slack.accounts.*.signingSecret'
        ),
    })


__all__ = [
    "normalize_optional_string",
    "has_configured_secret_input",
    "collect_telegram_webhook_secret_issues",
    "collect_slack_signing_secret_issues",
]
