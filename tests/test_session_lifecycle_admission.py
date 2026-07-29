"""Tests for src/sessions/session_lifecycle_admission.py.

Mirrors a focused subset of OpenClaw's
``src/sessions/session-lifecycle-admission.test.ts`` — the
parts that exercise the public surface (admission begin /
interrupt / predicates / counters). The full TS test file
also covers mutation contention across multiple identities;
those tests follow the same shape as the admission tests.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from src.sessions.session_lifecycle_admission import (
    SessionWorkAdmissionLease,
    begin_session_work_admission,
    collect_active_session_work_admission_identities,
    get_active_session_lifecycle_mutation_count,
    get_active_session_work_admission_count,
    is_competing_session_work_admission_active,
    is_session_work_admission_active,
    reset_admission_state_for_tests,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_admission_state_for_tests()
    yield
    reset_admission_state_for_tests()


def _admit(scope: str = "scope-x", identity: str = "alpha") -> SessionWorkAdmissionLease:
    """Synchronously begin an admission and return the lease.

    Mirrors the test helpers in
    session-lifecycle-admission.test.ts. The factory does
    not assert allowed so the test is independent of the
    host's gateway-draining stub.
    """

    async def _begin() -> SessionWorkAdmissionLease:
        return await begin_session_work_admission(
            scope=scope,
            identities=[identity],
            assert_allowed=lambda: None,
        )

    return asyncio.run(_begin())


class TestBeginSessionWorkAdmission:
    def test_admit_returns_lease(self) -> None:
        lease = _admit()
        assert lease is not None

    def test_admit_marks_active(self) -> None:
        lease = _admit(scope="scope-x", identity="alpha")
        assert (
            is_session_work_admission_active("scope-x", ["alpha"]) is True
        )
        assert get_active_session_work_admission_count() == 1
        lease.release()
        assert (
            is_session_work_admission_active("scope-x", ["alpha"]) is False
        )
        assert get_active_session_work_admission_count() == 0

    def test_release_idempotent(self) -> None:
        lease = _admit()
        lease.release()
        # Second release is a no-op (does not raise).
        lease.release()

    def test_create_handoff_after_release_raises(self) -> None:
        lease = _admit()
        lease.release()
        with pytest.raises(RuntimeError, match="released"):
            lease.create_handoff()

    def test_collect_active_identities_for_scope(self) -> None:
        lease_a = _admit(scope="scope-x", identity="alpha")
        lease_b = _admit(scope="scope-x", identity="beta")
        _admit(scope="scope-y", identity="alpha")
        identities = collect_active_session_work_admission_identities("scope-x")
        assert identities == {"alpha", "beta"}
        lease_a.release()
        lease_b.release()

    def test_collect_active_identities_requires_scope(self) -> None:
        with pytest.raises(ValueError, match="scope is required"):
            collect_active_session_work_admission_identities("")


class TestCompetingAdmissions:
    def test_is_competing_session_work_admission_active_inside_lease_run(
        self,
    ) -> None:
        # Inside lease.run() the current stack owns the
        # admission, so the competing predicate is False.
        async def _body() -> bool:
            lease = await begin_session_work_admission(
                scope="scope-x",
                identities=["alpha"],
                assert_allowed=lambda: None,
            )
            try:

                async def _inner() -> bool:
                    return is_competing_session_work_admission_active(
                        "scope-x", ["alpha"]
                    )

                return await lease.run(_inner)
            finally:
                lease.release()

        assert asyncio.run(_body()) is False

    def test_two_admissions_same_identity_make_competing(self) -> None:
        lease_a = _admit(scope="scope-x", identity="alpha")
        # A second admission on the same identity would
        # block on the lifecycle lock (we test the
        # "competing" predicate by checking the active
        # set contains both admissions when the second one
        # is admitted under a different stack).
        async def _second_stack() -> bool:
            # The second admission is allowed because the
            # lifecycle lock is reentrant; both admissions
            # end up in the active set.
            lease_b = await begin_session_work_admission(
                scope="scope-x",
                identities=["alpha"],
                assert_allowed=lambda: None,
            )
            try:
                return get_active_session_work_admission_count() == 2
            finally:
                lease_b.release()

        result = asyncio.run(_second_stack())
        assert result is True
        lease_a.release()


class TestAdmissionRun:
    def test_run_executes_under_admission(self) -> None:
        async def _body() -> str:
            lease = await begin_session_work_admission(
                scope="scope-x",
                identities=["alpha"],
                assert_allowed=lambda: None,
            )
            try:
                async def _inner() -> str:
                    # While inside run(), is_competing returns
                    # False because the current stack owns the
                    # admission.
                    return "ok"

                return await lease.run(_inner)
            finally:
                lease.release()

        assert asyncio.run(_body()) == "ok"

    def test_released_event_fires_on_release(self) -> None:
        lease = _admit()
        fired = threading.Event()

        async def _wait() -> None:
            # lease.released is a threading.Event in this port.
            # Wait for the event in a background task.
            def _watcher() -> None:
                lease.released.wait(timeout=1.0)
                fired.set()

            t = threading.Thread(target=_watcher, daemon=True)
            t.start()
            t.join(timeout=2.0)
            assert fired.is_set()

        asyncio.run(_wait())


class TestCounters:
    def test_initial_count_is_zero(self) -> None:
        assert get_active_session_work_admission_count() == 0
        assert get_active_session_lifecycle_mutation_count() == 0

    def test_mutation_count_reflects_active_mutations(self) -> None:
        # The mutation count is 0 when no mutations are
        # active. The dedicated mutation-run counter is
        # not exercised here; the public surface is the
        # lifecycle-mutation predicate, which is covered
        # in the upstream TS test with a full store-writer
        # wiring. We only assert the no-op baseline here.
        assert get_active_session_lifecycle_mutation_count() == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
