"""jarvis_agent.uuid7 — monotonic UUIDv7 session and entry identifiers.

OpenClaw parity: ``packages/agent-core/src/harness/session/uuid.ts``.

Why not ``uuid.uuid4()``
=======================
Session tree entries are ordered by id. The tree is an append-only log
where an entry's parent is identified by id, and replaying a branch means
walking ids in order. UUIDv7 puts a 48-bit big-endian millisecond
timestamp in the leading bytes, so lexicographic string order equals
creation order — and the session code relies on that instead of carrying a
separate sequence column.

Random v4 ids would still be unique but would sort arbitrarily, so a
transcript replayed from storage would come back shuffled. That failure is
silent: the ids look fine, the messages are all present, and only the
*order* is wrong.

Monotonicity within a millisecond
=================================
Two entries created in the same millisecond would share a timestamp
prefix, so the sequence counter breaks the tie. It is seeded from random
bytes at the start of each new millisecond and incremented otherwise; on
32-bit wraparound the timestamp is bumped so ordering still holds. This
mirrors the TypeScript exactly, including the module-level mutable state.
"""

from __future__ import annotations

import secrets
import threading
import time

#: Last millisecond timestamp handed out. Parity: ``lastTimestamp``.
#: Starts at ``-Infinity`` in the TS; ``-1`` is equivalent here because
#: ``Date.now()`` is always positive and the only use is a ``>`` compare.
_last_timestamp: int = -1

#: Tie-break counter within a millisecond. Parity: ``sequence``.
_sequence: int = 0

#: The TS runs single-threaded on an event loop, so its increments cannot
#: interleave. Python threads can. Under CPython's GIL the race is very
#: hard to observe (removing this lock does not fail the concurrency test),
#: so the lock is cheap insurance rather than a measured fix: it is what
#: keeps the uniqueness guarantee true on a free-threaded build, where the
#: GIL no longer supplies it. A duplicate id in a session tree means one
#: entry silently replacing another, so the guarantee is worth a mutex.
_lock = threading.Lock()

_UINT32_MASK = 0xFFFFFFFF


def _now_ms() -> int:
    """Current time in milliseconds. Parity: ``Date.now()``."""
    return int(time.time() * 1000)


def uuidv7() -> str:
    """Generate a monotonic UUIDv7 string. Parity: ``uuidv7()``.

    Guarantees, in the order they matter:

    1. Successive calls return strictly increasing strings, even inside a
       single millisecond and even if the system clock steps backwards.
    2. The first 48 bits are the creation timestamp in milliseconds, so
       lexicographic order is creation order.
    3. Version and variant nibbles are set (``7`` and ``0b10``), so the
       value is a well-formed RFC 9562 UUIDv7.
    """
    global _last_timestamp, _sequence

    random = bytearray(secrets.token_bytes(16))
    timestamp = _now_ms()

    with _lock:
        if timestamp > _last_timestamp:
            # New millisecond: reseed the counter from random bytes 6..10,
            # big-endian, matching `DataView.getUint32(0)` in the TS.
            _sequence = int.from_bytes(random[6:10], "big")
            _last_timestamp = timestamp
        else:
            # Same millisecond, or the clock went backwards. Either way the
            # previous timestamp is reused and the counter advances.
            _sequence = (_sequence + 1) & _UINT32_MASK
            if _sequence == 0:
                # Counter wrapped. Borrow from the timestamp so ordering
                # survives; ids stay ahead of real time by a millisecond.
                _last_timestamp += 1

        sequence = _sequence
        last_timestamp = _last_timestamp

    out = bytearray(16)
    # 48-bit big-endian millisecond timestamp.
    out[0] = (last_timestamp >> 40) & 0xFF
    out[1] = (last_timestamp >> 32) & 0xFF
    out[2] = (last_timestamp >> 24) & 0xFF
    out[3] = (last_timestamp >> 16) & 0xFF
    out[4] = (last_timestamp >> 8) & 0xFF
    out[5] = last_timestamp & 0xFF
    # Version 7 in the high nibble, then the sequence spread across the
    # remaining bits exactly as the TS lays it out.
    out[6] = 0x70 | ((sequence >> 28) & 0x0F)
    out[7] = (sequence >> 20) & 0xFF
    # RFC variant 0b10 in the top two bits.
    out[8] = 0x80 | ((sequence >> 14) & 0x3F)
    out[9] = (sequence >> 6) & 0xFF
    out[10] = ((sequence & 0x3F) << 2) | (random[10] & 0x03)
    out[11:16] = random[11:16]

    return _format_uuid(bytes(out))


def _format_uuid(data: bytes) -> str:
    """Render 16 bytes in canonical 8-4-4-4-12 form. Parity: ``formatUuid``."""
    hex_pairs = [f"{byte:02x}" for byte in data]
    return "-".join(
        (
            "".join(hex_pairs[0:4]),
            "".join(hex_pairs[4:6]),
            "".join(hex_pairs[6:8]),
            "".join(hex_pairs[8:10]),
            "".join(hex_pairs[10:16]),
        )
    )


def _reset_state_for_tests() -> None:
    """Reset the module counters. Test-only; not part of the TS surface."""
    global _last_timestamp, _sequence
    with _lock:
        _last_timestamp = -1
        _sequence = 0


__all__ = ["uuidv7"]
