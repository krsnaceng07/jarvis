"""Tests for src/sessions/session_work_admission_handoff.py.

Mirrors the public surface of OpenClaw's
``src/sessions/session-work-admission-handoff.ts`` (no
dedicated TS test file exists; the handoff is exercised
through ``session-lifecycle-admission.test.ts``). These tests
cover the contract directly so the port is locked down.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from src.sessions.session_work_admission_handoff import (
    HandoffSessionWorkAdmission,
    SessionWorkAdmissionLease,
    _reset_handoffs_for_tests,
    cancel_session_work_admission_handoff,
    clear_session_work_admission_handoffs,
    consume_session_work_admission_handoff,
    create_session_work_admission_handoff,
)


@pytest.fixture(autouse=True)
def _reset():
    _reset_handoffs_for_tests()
    yield
    _reset_handoffs_for_tests()


def _make_lease(released_event: asyncio.Event) -> SessionWorkAdmissionLease:
    def release() -> None:
        released_event.set()

    async def released() -> None:
        await released_event.wait()

    async def run(fn):
        return await fn()

    def create_handoff() -> str:
        return "nested-handoff"

    return SessionWorkAdmissionLease(
        create_handoff=create_handoff,
        release=release,
        released=released(),
        run=run,
    )


def _identity(scope: str, identity: str) -> str:
    """Return the JSON-encoded ``[scope, identity]`` form the registry uses."""
    return json.dumps([scope, identity], separators=(",", ":"))


def _make_admission(*identities: str) -> HandoffSessionWorkAdmission:
    return HandoffSessionWorkAdmission(
        handoff_ids=set(),
        identities=set(identities),
    )


class TestCreateAndConsumeHandoff:
    def test_create_returns_unique_token(self) -> None:
        a = _make_admission(_identity("scope-x", "alpha"))
        b = _make_admission(_identity("scope-x", "beta"))
        lease = _make_lease(asyncio.Event())
        token_a = create_session_work_admission_handoff(a, lease)
        token_b = create_session_work_admission_handoff(b, lease)
        assert token_a != token_b
        assert token_a in a.handoff_ids
        assert token_b in b.handoff_ids

    def test_consume_adopts_lease(self) -> None:
        a = _make_admission(
            _identity("scope-x", "alpha"), _identity("scope-x", "beta")
        )
        lease = _make_lease(asyncio.Event())
        token = create_session_work_admission_handoff(a, lease)
        adopted = consume_session_work_admission_handoff(
            handoff_id=token,
            scope="scope-x",
            identities=["alpha"],
        )
        assert adopted is lease
        # Single-use: the handoff is removed from both the
        # registry and the admission's handoff_ids set.
        assert token not in a.handoff_ids
        # A second consume on the same token returns None.
        again = consume_session_work_admission_handoff(
            handoff_id=token,
            scope="scope-x",
            identities=["alpha"],
        )
        assert again is None

    def test_consume_rejects_uncovered_identity(self) -> None:
        a = _make_admission(_identity("scope-x", "alpha"))
        lease = _make_lease(asyncio.Event())
        token = create_session_work_admission_handoff(a, lease)
        # "beta" is NOT in the admission's identities.
        adopted = consume_session_work_admission_handoff(
            handoff_id=token,
            scope="scope-x",
            identities=["beta"],
        )
        assert adopted is None
        # The handoff is still registered because the consume
        # was rejected.
        assert token in a.handoff_ids

    def test_consume_rejects_empty_identities(self) -> None:
        a = _make_admission(_identity("scope-x", "alpha"))
        lease = _make_lease(asyncio.Event())
        token = create_session_work_admission_handoff(a, lease)
        adopted = consume_session_work_admission_handoff(
            handoff_id=token,
            scope="scope-x",
            identities=[],
        )
        assert adopted is None
        assert token in a.handoff_ids

    def test_consume_rejects_blank_handoff_id(self) -> None:
        a = _make_admission(_identity("scope-x", "alpha"))
        lease = _make_lease(asyncio.Event())
        for blank in ("", "   ", "\t"):
            assert (
                consume_session_work_admission_handoff(
                    handoff_id=blank,
                    scope="scope-x",
                    identities=["alpha"],
                )
                is None
            )

    def test_consume_wires_interrupt_and_fires_when_already_interrupted(self) -> None:
        a = _make_admission(_identity("scope-x", "alpha"))
        a.interrupted = True
        lease = _make_lease(asyncio.Event())
        token = create_session_work_admission_handoff(a, lease)
        fired: list[int] = []
        adopted = consume_session_work_admission_handoff(
            handoff_id=token,
            scope="scope-x",
            identities=["alpha"],
            on_interrupt=lambda: fired.append(1),
        )
        assert adopted is lease
        # onInterrupt was wired AND fired because the
        # admission was already interrupted.
        assert a.interrupt is not None
        assert fired == [1]


class TestCancelHandoff:
    def test_cancel_releases_unconsumed_handoff(self) -> None:
        a = _make_admission(_identity("scope-x", "alpha"))
        event = asyncio.Event()
        lease = _make_lease(event)
        token = create_session_work_admission_handoff(a, lease)
        assert cancel_session_work_admission_handoff(token) is True
        # lease.release was called → released() resolves.
        async def _wait_released():
            await lease.released
            return True
        assert asyncio.run(_wait_released()) is True

    def test_cancel_returns_false_when_missing(self) -> None:
        assert cancel_session_work_admission_handoff("not-a-real-token") is False


class TestClearHandoffs:
    def test_clear_removes_all_handoffs_for_an_admission(self) -> None:
        a = _make_admission(_identity("scope-x", "alpha"))
        b = _make_admission(_identity("scope-x", "beta"))
        lease = _make_lease(asyncio.Event())
        token_a1 = create_session_work_admission_handoff(a, lease)
        token_a2 = create_session_work_admission_handoff(a, lease)
        token_b = create_session_work_admission_handoff(b, lease)
        clear_session_work_admission_handoffs(a)
        # a's handoffs are gone; b's handoff still registered.
        assert token_a1 not in a.handoff_ids
        assert token_a2 not in a.handoff_ids
        assert a.handoff_ids == set()
        assert token_b in b.handoff_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
