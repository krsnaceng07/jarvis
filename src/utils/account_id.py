"""jarvis.utils.account_id — account-id normalization wrapper.

OpenClaw parity: mirrors ``openclaw-main/src/utils/account-id.ts``.

Public surface:

- :func:`normalize_account_id`
"""
from __future__ import annotations

from typing import Optional

#: Re-export of routing's normalize_optional_account_id.
from src.routing.account_id import normalize_optional_account_id  # noqa: F401


def normalize_account_id(value: Optional[str]) -> Optional[str]:
    """Compatibility wrapper for account-id normalization.

    Mirrors :func:`normalizeAccountId` (``utils/account-id.ts``).
    """
    return normalize_optional_account_id(value)


__all__ = ["normalize_account_id"]
