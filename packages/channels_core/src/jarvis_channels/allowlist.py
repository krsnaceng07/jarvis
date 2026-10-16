"""Channel allowlist — restrict inbound messages to approved senders.

Mirrors OpenClaw's ``src/channels/allow-from.ts`` +
``src/channels/allowlist-match.ts``.

The operator configures an ``allow_from`` list per channel in
``~/.jarvis/config.json``. Inbound messages from users NOT on the list
are silently dropped (never dispatched to the agent).

Policy variants:
  - ``"*"`` or ``[]`` — accept from everyone (no allowlist).
  - ``["12345", "67890"]`` — accept only those chat/user ids.
  - ``["@username"]`` — accept by Telegram username (if the
    channel resolves it).

The function ``is_allowed()`` is channel-agnostic; each channel plugin
passes its own sender id and the configured list.
"""

from __future__ import annotations

import re
from typing import Any


# ── Types ──────────────────────────────────────────────────────────────


# An allowlist entry is a string id, "@handle", or "*".
AllowlistEntry = str

# Sentinel value meaning "allow all".
ALLOW_ALL = "*"


class AllowlistPolicy(list[AllowlistEntry]):
    """Channel allowlist policy containing allowed sender ids or usernames.

    Inherits from list[str] for 100% backward compatibility with list operations,
    while supporting OpenClaw-parity keyword initialization and .is_allowed() method.
    """

    def __init__(
        self,
        entries: object | None = None,
        *,
        allowed_senders: set[str] | list[str] | None = None,
    ) -> None:
        items: list[str] = []
        if allowed_senders is not None:
            items = [str(x) for x in allowed_senders]
        elif entries is not None:
            if isinstance(entries, str):
                items = [e.strip() for e in entries.split(",") if e.strip()]
            elif isinstance(entries, (list, tuple, set)):
                items = [str(x) for x in entries]
        super().__init__(items)

    def is_allowed(self, sender_id: str, sender_username: str | None = None) -> bool:
        """Evaluate if a sender passes this allowlist policy."""
        return is_allowed(sender_id, sender_username, self)


# ── Core matcher ───────────────────────────────────────────────────────


def is_allowed(
    sender_id: str,
    sender_username: str | None,
    policy: AllowlistPolicy | str | None,
) -> bool:
    """Return True if ``sender_id`` (or ``sender_username``) passes the policy.

    Parameters
    ----------
    sender_id : str
        Channel-native user/chat id (e.g. Telegram user_id as a string).
    sender_username : str | None
        Optional channel-native username (e.g. ``"@alice"`` or ``"alice"``).
        Normalized to ``"@<lower>"`` before comparison.
    policy : list[str] | str | None
        The allow-from config value. ``None`` or ``"*"`` or ``[]`` means
        allow everyone.

    Returns
    -------
    bool
        ``True`` if the sender is allowed.
    """
    # Empty / None / "*" → allow all.
    if policy is None:
        return True
    if isinstance(policy, str):
        return policy.strip() == ALLOW_ALL
    if not policy:
        return True
    if ALLOW_ALL in policy:
        return True

    # Normalize sender username for comparison.
    norm_username: str | None = None
    if sender_username:
        norm_username = "@" + sender_username.lstrip("@").lower()

    for entry in policy:
        entry = entry.strip()
        if not entry:
            continue
        if entry == ALLOW_ALL:
            return True
        # Username match (@handle).
        if entry.startswith("@"):
            if norm_username and norm_username == entry.lower():
                return True
        else:
            # Plain id match (exact string).
            if entry == sender_id:
                return True

    return False


def normalize_allowlist(raw: object) -> AllowlistPolicy | None:
    """Normalize a raw config value to an ``AllowlistPolicy`` or ``None``.

    Accepts:
      - ``None`` → ``None`` (allow all)
      - ``"*"`` → ``None`` (allow all)
      - ``""`` → ``None`` (allow all)
      - ``"id1,id2"`` → ``["id1", "id2"]``
      - ``["id1", "id2"]`` → ``["id1", "id2"]``
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped or stripped == ALLOW_ALL:
            return None
        # Comma-separated ids.
        return AllowlistPolicy([e.strip() for e in re.split(r"[,\s]+", stripped) if e.strip()])
    if isinstance(raw, list):
        entries = [str(e).strip() for e in raw if str(e).strip()]
        if not entries or ALLOW_ALL in entries:
            return None
        return AllowlistPolicy(entries)
    return None


def enforce_dm_policy(
    sender_id: str,
    sender_username: str | None,
    policy_str: str,
    allowlist: AllowlistPolicy | str | None,
    channel_id: str,
    account_id: str,
    pairing_store: Any | None = None,
) -> tuple[bool, str | None]:
    """Enforce the DM policy, including pairing flow.

    Returns:
        (is_allowed: bool, pairing_message: str | None)
    """
    # If the sender is explicitly on the allowlist or policy is fully open.
    if is_allowed(sender_id, sender_username, allowlist):
        return True, None

    if policy_str == "allowlist":
        return False, None
    elif policy_str == "deny":
        return False, None
    elif policy_str == "pairing":
        # Check explicit pairing allowlist via database
        if pairing_store and pairing_store.is_approved(channel_id, account_id, sender_id):
            return True, None

        # If not approved, generate a request
        if pairing_store:
            code = pairing_store.request_pairing(channel_id, account_id, sender_id)
            if code:
                msg = (
                    f"Your pairing code is {code}\n\n"
                    f"Please provide this code to the operator to approve your device/account."
                )
                return False, msg

        return False, None

    return False, None


__all__ = [
    "ALLOW_ALL",
    "AllowlistEntry",
    "AllowlistPolicy",
    "is_allowed",
    "normalize_allowlist",
    "enforce_dm_policy",
]
