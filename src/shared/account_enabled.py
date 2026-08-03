"""jarvis.shared.account_enabled — account-enabled predicate.

OpenClaw parity: mirrors ``openclaw-main/src/shared/account-enabled.ts``.
"""
from __future__ import annotations

from typing import Any


def is_account_enabled(account: Any) -> bool:
    """Return True when the account is missing or has ``enabled`` not set to ``False``.

    Mirrors :func:`isAccountEnabled` (``shared/account-enabled.ts``).
    """
    if not account or not isinstance(account, dict):
        return True
    enabled = account.get("enabled")
    return enabled is not False


__all__ = ["is_account_enabled"]
