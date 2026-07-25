"""Phase 5.8 gate: ``uuid7.py`` monotonicity and format.

``uuid.ts`` has no test file in OpenClaw, so these vectors are derived
from the plan's stated check — "``uuidv7`` monotonicity and
timestamp-prefix ordering" — and from the RFC 9562 layout the TS encodes.

The property that actually matters is ordering: ids must sort in creation
order, because the session tree uses id order *as* transcript order. A
generator that is unique but not ordered passes every uniqueness test and
still shuffles replayed conversations.
"""

from __future__ import annotations

import re
import threading

from jarvis_agent import uuid7 as uuid7_module
from jarvis_agent.uuid7 import uuidv7

_CANONICAL = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def _reset() -> None:
    """Restore module counters and the real clock.

    Called explicitly at the top of each test rather than via an autouse
    fixture: these tests replace ``_now_ms``, and an explicit reset makes
    the ordering dependency between them impossible to miss.
    """
    import time as _time

    uuid7_module._now_ms = lambda: int(_time.time() * 1000)  # type: ignore[assignment]
    uuid7_module._reset_state_for_tests()


def test_format_is_canonical_uuidv7() -> None:
    """Version nibble is 7 and the variant nibble is one of 8/9/a/b."""
    _reset()
    for _ in range(200):
        value = uuidv7()
        assert _CANONICAL.match(value), value
        assert len(value) == 36


def test_ids_are_unique() -> None:
    _reset()
    values = [uuidv7() for _ in range(5000)]
    assert len(set(values)) == len(values)


def test_ids_are_strictly_increasing_as_strings() -> None:
    """The load-bearing property: lexicographic order == creation order.

    5000 iterations run well inside one millisecond on any modern machine,
    so this exercises the same-millisecond sequence path rather than just
    the timestamp path.
    """
    _reset()
    values = [uuidv7() for _ in range(5000)]
    assert values == sorted(values)
    for earlier, later in zip(values[:-1], values[1:], strict=True):
        assert earlier < later


def test_timestamp_prefix_encodes_current_time() -> None:
    """First 48 bits are the creation time in milliseconds."""
    _reset()
    before = uuid7_module._now_ms()
    value = uuidv7()
    after = uuid7_module._now_ms()

    hex_prefix = value[:8] + value[9:13]
    encoded_ms = int(hex_prefix, 16)
    assert before <= encoded_ms <= after


def test_ordering_survives_a_backwards_clock() -> None:
    """A clock that steps backwards must not produce a smaller id.

    NTP corrections and VM suspend/resume both do this in practice. The
    TS handles it by reusing ``lastTimestamp`` whenever the observed time
    is not greater, and this asserts the ported behaviour.
    """
    _reset()
    fake_time = [1_000_000_000_000]
    uuid7_module._now_ms = lambda: fake_time[0]  # type: ignore[assignment]
    try:
        first = uuidv7()
        fake_time[0] -= 60_000  # clock jumps a minute into the past
        second = uuidv7()
        third = uuidv7()
        assert first < second < third
    finally:
        _reset()


def test_sequence_wraparound_bumps_the_timestamp() -> None:
    """When the 32-bit counter wraps, the timestamp borrows one ms.

    Without the bump, the wrapped id would sort *before* its predecessor
    and break ordering at exactly the moment the system is busiest.
    """
    _reset()
    fake_time = [1_000_000_000_000]
    uuid7_module._now_ms = lambda: fake_time[0]  # type: ignore[assignment]
    try:
        uuidv7()
        # Drive the counter to its maximum so the next call must wrap.
        with uuid7_module._lock:
            uuid7_module._sequence = 0xFFFFFFFF
            timestamp_before = uuid7_module._last_timestamp
        before_id = uuidv7()
        with uuid7_module._lock:
            assert uuid7_module._sequence == 0
            assert uuid7_module._last_timestamp == timestamp_before + 1
        after_id = uuidv7()
        assert before_id < after_id
    finally:
        _reset()


def test_concurrent_generation_stays_unique() -> None:
    """Threads must not be able to hand out a duplicate id.

    Scope of this test, stated honestly: it is a smoke test, not a proof.
    Removing ``_lock`` from ``uuid7.py`` does **not** make it fail — the
    counter increment is a handful of bytecodes and CPython's GIL makes
    the interleaving essentially unobservable (measured: 48,000 ids across
    16 threads with ``setswitchinterval(1e-9)`` produced zero duplicates
    unlocked). The lock is kept anyway because it is nearly free and the
    guarantee must survive a free-threaded build, where the GIL no longer
    provides it. Treat a pass here as "no gross breakage", not as evidence
    the locking is correct.
    """
    _reset()
    collected: list[list[str]] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        collected.append([uuidv7() for _ in range(500)])

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    flat = [value for batch in collected for value in batch]
    assert len(flat) == 8 * 500
    assert len(set(flat)) == len(flat), "duplicate id generated under concurrency"


def test_reset_helper_is_not_part_of_the_public_surface() -> None:
    """``__all__`` exports only ``uuidv7``; helpers are private by name."""
    assert uuid7_module.__all__ == ["uuidv7"]
