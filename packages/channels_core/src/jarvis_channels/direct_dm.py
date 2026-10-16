"""Direct message (DM) security policy and pairing management.

Mirrors OpenClaw's ``src/channels/direct-dm.ts`` and ``src/channels/direct-dm-access.ts``.

Policies:
- ``"open"``: Any external user can initiate a DM turn.
- ``"allowlist"``: Only explicitly listed user IDs or handles can DM the bot.
- ``"pairing"``: Unknown users must complete an operator pairing approval flow before turns run.
- ``"block"`` / ``"disabled"``: Inbound DMs are disabled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DirectDmPolicyKind = Literal["open", "allowlist", "pairing", "block", "disabled"]
DirectDmDecisionKind = Literal["allow", "block", "pairing"]

DM_POLICY_OPEN = "dm_policy_open"
DM_POLICY_DISABLED = "dm_policy_disabled"
DM_POLICY_ALLOWLISTED = "dm_policy_allowlisted"
DM_POLICY_PAIRING_REQUIRED = "dm_policy_pairing_required"
DM_POLICY_NOT_ALLOWLISTED = "dm_policy_not_allowlisted"


@dataclass(frozen=True, slots=True)
class DirectDmAccessDecision:
    """Outcome of DM ingress access policy evaluation."""

    decision: DirectDmDecisionKind
    reason_code: str
    reason: str
    effective_allow_from: tuple[str, ...] = field(default_factory=tuple)


def resolve_inbound_direct_dm_access(
    sender_id: str,
    sender_username: str | None = None,
    dm_policy: DirectDmPolicyKind = "pairing",
    allow_from: list[str] | set[str] | tuple[str, ...] | None = None,
    paired_senders: set[str] | None = None,
) -> DirectDmAccessDecision:
    """Evaluate direct DM ingress security policy for a sender."""
    effective_allow = tuple(str(x) for x in allow_from) if allow_from else ()
    paired = paired_senders or set()

    if dm_policy in ("block", "disabled"):
        return DirectDmAccessDecision(
            decision="block",
            reason_code=DM_POLICY_DISABLED,
            reason="Direct messages are disabled for this channel.",
            effective_allow_from=effective_allow,
        )

    if dm_policy == "open":
        return DirectDmAccessDecision(
            decision="allow",
            reason_code=DM_POLICY_OPEN,
            reason="Channel direct message policy is open.",
            effective_allow_from=effective_allow,
        )

    # Check explicit allowlist
    norm_id = sender_id.strip()
    norm_user = f"@{sender_username.strip().lstrip('@').lower()}" if sender_username else None

    is_explicitly_allowed = (
        "*" in effective_allow
        or norm_id in effective_allow
        or (norm_user is not None and norm_user.lower() in [x.lower() for x in effective_allow])
    )

    if is_explicitly_allowed:
        return DirectDmAccessDecision(
            decision="allow",
            reason_code=DM_POLICY_ALLOWLISTED,
            reason="Sender is explicitly allowlisted for direct messages.",
            effective_allow_from=effective_allow,
        )

    # Check paired senders
    if norm_id in paired or (norm_user and norm_user.lower() in paired):
        return DirectDmAccessDecision(
            decision="allow",
            reason_code=DM_POLICY_ALLOWLISTED,
            reason="Sender has an active verified pairing record.",
            effective_allow_from=effective_allow,
        )

    # Pairing mode sends a pairing prompt
    if dm_policy == "pairing":
        return DirectDmAccessDecision(
            decision="pairing",
            reason_code=DM_POLICY_PAIRING_REQUIRED,
            reason="Sender requires operator pairing approval.",
            effective_allow_from=effective_allow,
        )

    # Fallback for allowlist mode: block
    return DirectDmAccessDecision(
        decision="block",
        reason_code=DM_POLICY_NOT_ALLOWLISTED,
        reason="Sender is not authorized by channel allowlist.",
        effective_allow_from=effective_allow,
    )


__all__ = [
    "DM_POLICY_ALLOWLISTED",
    "DM_POLICY_DISABLED",
    "DM_POLICY_NOT_ALLOWLISTED",
    "DM_POLICY_OPEN",
    "DM_POLICY_PAIRING_REQUIRED",
    "DirectDmAccessDecision",
    "DirectDmDecisionKind",
    "DirectDmPolicyKind",
    "resolve_inbound_direct_dm_access",
]
