"""Session work-admission handoff helpers.

Mirrors OpenClaw's ``src/sessions/session-work-admission-handoff.ts``:

- A handoff is a process-wide single-use token that lets one
  bundled chunk adopt a work-admission lease from another
  chunk over an in-process RPC.
- The opaque token is single-use; the requester must supply
  identities that are covered by the lease. Adoption is
  atomic: the lease is moved from the original admission
  context to the adopter on a successful ``consume``.

Public surface (mirrors the TS source):
- ``create_session_work_admission_handoff`` — register a
  handoff for an admission+lease pair, returns the token
- ``consume_session_work_admission_handoff`` — atomically
  adopt a lease across an in-process RPC
- ``cancel_session_work_admission_handoff`` — release a
  handoff that was never consumed

Python adaptations (documented in code):
- TS ``crypto.randomUUID()`` → Python ``uuid.uuid4()``
- TS ``Set<string>`` (insertion-ordered) → Python ``set``
  (membership only; we do not rely on iteration order here)
- TS ``Map<key, value>`` → Python ``dict``
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Optional

from shared.global_singleton import resolve_global_singleton

from src.sessions.session_lifecycle_identity import normalize_session_identities


@dataclass
class SessionWorkAdmissionLease:
    """Lease returned by a work-admission handoff.

    Mirrors the TS ``SessionWorkAdmissionLease`` type.
    """

    create_handoff: Callable[[], str]
    release: Callable[[], None]
    released: Awaitable[None]
    run: Callable[[Callable[[], Awaitable[Any]]], Awaitable[Any]]


@dataclass
class HandoffSessionWorkAdmission:
    """Admission context backing a handoff.

    Mirrors the TS ``HandoffSessionWorkAdmission`` type.
    """

    handoff_ids: set[str] = field(default_factory=set)
    identities: set[str] = field(default_factory=set)
    interrupt: Optional[Callable[[], None]] = None
    interrupted: bool = False


@dataclass
class _SessionWorkAdmissionHandoff:
    """Internal record of an in-flight handoff.

    Mirrors the TS ``SessionWorkAdmissionHandoff`` type.
    """

    admission: HandoffSessionWorkAdmission
    lease: SessionWorkAdmissionLease


# Process-wide handoff registry. Mirrors the TS singleton.
_HANDOFFS_KEY = "openclaw.sessionWorkAdmissionHandoffs"
_HANDOFFS: dict[str, _SessionWorkAdmissionHandoff] = resolve_global_singleton(
    _HANDOFFS_KEY, lambda: {}
)


def create_session_work_admission_handoff(
    admission: HandoffSessionWorkAdmission,
    lease: SessionWorkAdmissionLease,
) -> str:
    """Register a handoff for an admission+lease pair.

    Mirrors ``createSessionWorkAdmissionHandoff``. Returns the
    opaque single-use token.
    """
    handoff_id = str(uuid.uuid4())
    admission.handoff_ids.add(handoff_id)
    _HANDOFFS[handoff_id] = _SessionWorkAdmissionHandoff(admission=admission, lease=lease)
    return handoff_id


def clear_session_work_admission_handoffs(
    admission: HandoffSessionWorkAdmission,
) -> None:
    """Remove every handoff registered against ``admission``.

    Mirrors ``clearSessionWorkAdmissionHandoffs``.
    """
    for handoff_id in list(admission.handoff_ids):
        _HANDOFFS.pop(handoff_id, None)
    admission.handoff_ids.clear()


def consume_session_work_admission_handoff(
    *,
    handoff_id: str,
    scope: str,
    identities: Iterable[Optional[str]],
    on_interrupt: Optional[Callable[[], None]] = None,
) -> Optional[SessionWorkAdmissionLease]:
    """Atomically adopt a previously admitted work lease.

    Mirrors ``consumeSessionWorkAdmissionHandoff``. The token
    is single-use; requested identities must all be covered
    by the lease. On success the lease is moved from the
    original admission context to the adopter and the
    ``onInterrupt`` callback is wired.
    """
    normalized_handoff_id = (handoff_id or "").strip()
    if not normalized_handoff_id:
        return None
    handoff = _HANDOFFS.get(normalized_handoff_id)
    if handoff is None:
        return None
    normalized_identities = normalize_session_identities(scope, identities)
    if not normalized_identities or any(
        identity not in handoff.admission.identities
        for identity in normalized_identities
    ):
        return None
    _HANDOFFS.pop(normalized_handoff_id, None)
    handoff.admission.handoff_ids.discard(normalized_handoff_id)
    handoff.admission.interrupt = on_interrupt
    if handoff.admission.interrupted and on_interrupt is not None:
        on_interrupt()
    return handoff.lease


def cancel_session_work_admission_handoff(handoff_id: str) -> bool:
    """Release a handoff that was never consumed; the adopter owns consumed leases.

    Mirrors ``cancelSessionWorkAdmissionHandoff``. Returns
    ``True`` when a handoff was found and released, ``False``
    otherwise.
    """
    normalized_handoff_id = (handoff_id or "").strip()
    handoff = _HANDOFFS.get(normalized_handoff_id)
    if handoff is None:
        return False
    _HANDOFFS.pop(normalized_handoff_id, None)
    handoff.admission.handoff_ids.discard(normalized_handoff_id)
    handoff.lease.release()
    return True


__all__ = [
    "HandoffSessionWorkAdmission",
    "SessionWorkAdmissionLease",
    "_reset_handoffs_for_tests",
    "cancel_session_work_admission_handoff",
    "clear_session_work_admission_handoffs",
    "consume_session_work_admission_handoff",
    "create_session_work_admission_handoff",
]


def _reset_handoffs_for_tests() -> None:
    """Clear the process-wide handoff registry. Test-only helper."""
    _HANDOFFS.clear()
