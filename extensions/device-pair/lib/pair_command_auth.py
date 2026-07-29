"""Device Pair pair-command auth helpers.

Mirrors OpenClaw's ``extensions/device-pair/pair-command-auth.ts``.

Determines the per-caller authorization state for the
``/pair`` command family. Internal gateway callers
(webchat or RPC with explicit ``gatewayClientScopes``)
are checked against the documented operator scopes;
external channel callers fall back to a sender-is-owner
check so the owner can approve a pairing request from
their own channel without holding the full operator
scope bundle.

Public surface (mirrors the TS source):
- ``resolve_pairing_command_auth_state(params)`` — the
  per-caller auth state used by the pair-command
  approve flow
- ``build_missing_pairing_scope_reply`` — reply helper
  for the missing-pairing-scope error
- ``build_missing_setup_handoff_scope_reply`` — reply
  helper for the missing-setup-handoff-scope error

Python adaptations (documented in code):
- TS string-literal unions → Python ``Literal[...]`` +
  ``frozenset`` membership sets
"""
from __future__ import annotations

from typing import Literal, Optional, TypedDict


# Scope constants (mirrors the TS source).
COMMAND_OWNER_PAIRING_SCOPES: tuple[str, ...] = ("operator.pairing",)
PAIRING_SCOPE = "operator.pairing"
ADMIN_SCOPE = "operator.admin"
TALK_SECRETS_SCOPE = "operator.talk.secrets"

# Re-export for downstream tests / helpers.
PAIRING_SCOPES: frozenset[str] = frozenset({PAIRING_SCOPE, ADMIN_SCOPE})
SETUP_HANDOFF_SCOPES: frozenset[str] = frozenset({TALK_SECRETS_SCOPE, ADMIN_SCOPE})


# ── Types ──────────────────────────────────────────────────


class PairingCommandAuthParams(TypedDict, total=False):
    channel: str
    gatewayClientScopes: list[str]
    senderIsOwner: bool


class PairingCommandAuthState(TypedDict, total=False):
    isInternalGatewayCaller: bool
    isMissingPairingPrivilege: bool
    isMissingSetupHandoffPrivilege: bool
    canIssueFullAccessSetup: bool
    approvalCallerScopes: list[str]


# ── Helpers ──────────────────────────────────────────────


def _is_internal_gateway_pairing_caller(params: PairingCommandAuthParams) -> bool:
    """Return ``True`` when the caller is a webchat or RPC gateway client.

    Mirrors the private ``isInternalGatewayPairingCaller`` helper.
    """
    if params.get("channel") == "webchat":
        return True
    return isinstance(params.get("gatewayClientScopes"), list)


def _has_pairing_privilege(scopes: list[str]) -> bool:
    """Return ``True`` when ``scopes`` covers the pairing privilege.

    Mirrors the private ``hasPairingPrivilege`` helper.
    """
    return PAIRING_SCOPE in scopes or ADMIN_SCOPE in scopes


def _has_setup_handoff_privilege(scopes: list[str]) -> bool:
    """Return ``True`` when ``scopes`` covers the setup-handoff privilege.

    Mirrors the private ``hasSetupHandoffPrivilege`` helper.
    """
    return TALK_SECRETS_SCOPE in scopes or ADMIN_SCOPE in scopes


# ── Public surface ──────────────────────────────────────────


def resolve_pairing_command_auth_state(
    params: PairingCommandAuthParams,
) -> PairingCommandAuthState:
    """Resolve the per-caller pairing-command auth state.

    Mirrors ``resolvePairingCommandAuthState``. The state
    drives the per-caller missing-scope replies in the
    pair-command flow.
    """
    if _is_internal_gateway_pairing_caller(params):
        scopes = (
            params["gatewayClientScopes"]
            if isinstance(params.get("gatewayClientScopes"), list)
            else []
        )
        return {
            "isInternalGatewayCaller": True,
            "isMissingPairingPrivilege": not _has_pairing_privilege(scopes),
            "isMissingSetupHandoffPrivilege": not _has_setup_handoff_privilege(scopes),
            "canIssueFullAccessSetup": ADMIN_SCOPE in scopes,
            "approvalCallerScopes": list(scopes),
        }
    if params.get("senderIsOwner") is True:
        return {
            "isInternalGatewayCaller": False,
            "isMissingPairingPrivilege": False,
            "isMissingSetupHandoffPrivilege": False,
            "canIssueFullAccessSetup": True,
            "approvalCallerScopes": list(COMMAND_OWNER_PAIRING_SCOPES),
        }
    return {
        "isInternalGatewayCaller": False,
        "isMissingPairingPrivilege": True,
        "isMissingSetupHandoffPrivilege": True,
        "canIssueFullAccessSetup": False,
    }


def build_missing_pairing_scope_reply() -> dict[str, str]:
    """Build the user-facing reply for the missing-pairing-scope error.

    Mirrors ``buildMissingPairingScopeReply``.
    """
    return {"text": "⚠️ This command requires operator.pairing."}


def build_missing_setup_handoff_scope_reply() -> dict[str, str]:
    """Build the user-facing reply for the missing-setup-handoff-scope error.

    Mirrors ``buildMissingSetupHandoffScopeReply``.
    """
    return {
        "text": "⚠️ Setup code handoff includes Talk secrets and requires operator.talk.secrets."
    }


__all__ = [
    "ADMIN_SCOPE",
    "COMMAND_OWNER_PAIRING_SCOPES",
    "PAIRING_SCOPE",
    "PAIRING_SCOPES",
    "PairingCommandAuthParams",
    "PairingCommandAuthState",
    "SETUP_HANDOFF_SCOPES",
    "TALK_SECRETS_SCOPE",
    "build_missing_pairing_scope_reply",
    "build_missing_setup_handoff_scope_reply",
    "resolve_pairing_command_auth_state",
]
