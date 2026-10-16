"""Device Pair pair-command approve helpers.

Mirrors OpenClaw's ``extensions/device-pair/pair-command-approve.ts``.

Public surface (mirrors the TS source):
- ``select_pending_approval_request`` — pick one
  pending request by id, by ``"latest"``, or just the
  first one
- ``approve_pending_pairing_request`` — approve a
  pending pairing request and return the user-facing
  reply

Python adaptations (documented in code):
- TS Promise-returning ``approveDevicePairing`` →
  Python async ``approve_device_pairing`` injected via
  the ``approve_device_pairing`` parameter (production
  wiring is the responsibility of the host)
- TS string-literal unions → Python ``Literal[...]``
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional, TypedDict, Union

from jarvis_normalization_core.string_coerce import (
    normalize_lowercase_string_or_empty,
    normalize_optional_string,
)


# ── Type aliases (mirrors the TS source shapes) ────────────


PendingPairingEntry = dict[str, Any]
ApprovedPairingEntry = dict[str, Any]
ForbiddenPairingEntry = dict[str, Any]
ApprovePairingResult = Optional[Union[ApprovedPairingEntry, ForbiddenPairingEntry]]


class ApprovePairingRequest(TypedDict, total=False):
    requestId: str
    callerScopes: list[str]


class SelectPendingParams(TypedDict, total=False):
    pending: list[PendingPairingEntry]
    requested: str


class SelectPendingResult(TypedDict, total=False):
    pending: PendingPairingEntry
    reply: dict[str, str]


# ── Helpers ──────────────────────────────────────────────


def _build_multiple_pending_approval_reply(
    pending: list[PendingPairingEntry],
) -> dict[str, str]:
    """Build the "multiple pending requests" user-facing reply.

    Mirrors the private ``buildMultiplePendingApprovalReply`` helper.
    The header text is supplied by ``format_pending_requests`` from
    ``notify.ts`` (not ported yet — callers inject the
    ``format_pending_requests`` hook in the follow-up commit).
    """
    return {
        "text": (
            "Multiple pending requests found. Approve one explicitly:\n"
            "/pair approve <requestId>\n"
            "Or approve the most recent:\n"
            "/pair approve latest"
        )
    }


def _format_approved_pairing_reply(
    approved: ApprovedPairingEntry,
) -> dict[str, str]:
    """Build the "paired" user-facing reply.

    Mirrors the private ``formatApprovedPairingReply`` helper.
    """
    device = approved.get("device") or {}
    label = normalize_optional_string(device.get("displayName")) or device.get("deviceId", "")
    platform = normalize_optional_string(device.get("platform"))
    platform_label = f" ({platform})" if platform else ""
    return {"text": f"✅ Paired {label}{platform_label}."}


def _format_forbidden_pairing_requirement(approved: ForbiddenPairingEntry) -> str:
    """Build the "requires X to approve" message for a forbidden reply.

    Mirrors the private ``formatForbiddenPairingRequirement`` helper.
    """
    return approved.get("scope") or approved.get("role") or "additional approval"


# ── Public surface ──────────────────────────────────────────


def select_pending_approval_request(
    params: SelectPendingParams,
) -> SelectPendingResult:
    """Pick one pending request to approve.

    Mirrors ``selectPendingApprovalRequest``. The
    selection rules:
    1. No pending requests → ``{"reply": "No pending requests"}``.
    2. No ``requested`` and a single pending → that one.
    3. No ``requested`` and multiple pending → "multiple
       pending" reply (caller asks for a specific id).
    4. ``requested == "latest"`` → the request with the
       highest ``ts``.
    5. Otherwise → the request whose ``requestId`` matches.

    The TS source also renders the ``format_pending_requests``
    header; the Python port's no-header fallback is a
    minimal helper until the ``notify.ts`` port lands.
    """
    pending = params.get("pending") or []
    if not pending:
        return {"reply": {"text": "No pending device pairing requests."}}
    first, *rest = pending
    requested = params.get("requested")
    if not requested:
        if not rest:
            return {"pending": first}
        return {"reply": _build_multiple_pending_approval_reply(pending)}
    if normalize_lowercase_string_or_empty(requested) == "latest":
        latest = first
        for entry in rest:
            if (entry.get("ts") or 0) > (latest.get("ts") or 0):
                latest = entry
        return {"pending": latest}
    found = next(
        (entry for entry in pending if entry.get("requestId") == requested),
        None,
    )
    return (
        {"pending": found}
        if found is not None
        else {"reply": {"text": "Pairing request not found."}}
    )


async def approve_pending_pairing_request(
    params: ApprovePairingRequest,
    *,
    approve_device_pairing: Callable[
        [str, Optional[dict[str, Any]]],
        Awaitable[ApprovePairingResult],
    ],
) -> dict[str, str]:
    """Approve a pending pairing request and return the user-facing reply.

    Mirrors ``approvePendingPairingRequest``. The
    ``approve_device_pairing`` callable is the
    host-supplied approval primitive (production wiring
    is the responsibility of the host when the bootstrap
    SDK lands).
    """
    request_id = params.get("requestId", "")
    caller_scopes = params.get("callerScopes")
    if caller_scopes is None:
        result = await approve_device_pairing(request_id, None)
    else:
        result = await approve_device_pairing(request_id, {"callerScopes": list(caller_scopes)})
    if not result:
        return {"text": "Pairing request not found."}
    if result.get("status") == "forbidden":
        return {
            "text": (
                f"⚠️ This command requires "
                f"{_format_forbidden_pairing_requirement(result)} "
                f"to approve this pairing request."
            )
        }
    return _format_approved_pairing_reply(result)


__all__ = [
    "approve_pending_pairing_request",
    "select_pending_approval_request",
]
