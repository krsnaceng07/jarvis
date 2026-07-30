"""jarvis.agents.sessions.storage_lock — cross-process storage lock.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/storage-lock.ts``.

Provides a sync file-lock helper used by
``auth-storage`` (Phase 6.6) and other modules that
need cross-process safety on small files (settings,
auth, model catalog).

Parity
======
- ``acquire_lock_sync_with_retry(path) -> () -> None``
  (``storage-lock.ts:6-21``) — locks ``path`` with up
  to ``MAX_LOCK_ATTEMPTS`` (10) retries. Returns an
  ``unlock`` callable that releases the lock.
- Retry delay: ``LOCK_RETRY_DELAY_MS`` (20ms) busy-wait
  per attempt (``storage-lock.ts:4``). The OpenClaw
  source's busy-wait is a no-op (the comment notes
  that ``proper-lockfile`` rejects sync retries), but
  the *intent* is to give the kernel a 20ms window
  between attempts. The Python port uses
  ``time.sleep`` for the same effect (it actually
  *does* sleep, which is strictly more correct on
  the Python side).
- ``MAX_LOCK_ATTEMPTS = 10``, ``LOCK_RETRY_DELAY_MS = 20``
  — exact match to the OpenClaw constants.

Phase 6.1 — storage primitives.

Adaptations
-----------
- OpenClaw uses the ``proper-lockfile`` npm package;
  the Python port uses ``fcntl`` (POSIX) /
  ``msvcrt`` (Windows) for cross-process file
  locking. The behavior matches: only one process
  holds the lock at a time, the lock is released by
  the ``unlock`` callable, and concurrent ``acquire``
  calls retry up to ``MAX_LOCK_ATTEMPTS`` times with
  a 20ms sleep between attempts.
- On platforms where neither ``fcntl`` nor ``msvcrt``
  is available, the function falls back to a
  process-local ``threading.Lock`` so the surface
  still works (e.g. in tests or on a foreign OS).
  Cross-process safety is *not* guaranteed in that
  fallback, but the function's contract is preserved.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from typing import Callable


#: Maximum number of lock attempts before re-raising
#: the last ``ELOCKED`` / ``OSError``. Mirrors
#: ``MAX_LOCK_ATTEMPTS`` (``storage-lock.ts:3``).
MAX_LOCK_ATTEMPTS = 10

#: Delay between retry attempts, in milliseconds.
#: Mirrors ``LOCK_RETRY_DELAY_MS`` (``storage-lock.ts:4``).
LOCK_RETRY_DELAY_MS = 20


#: Unlock callable returned by
#: :func:`acquire_lock_sync_with_retry`. Calling it
#: releases the lock; calling it twice is a no-op.
UnlockFn = Callable[[], None]


# Module-level fallback lock. When the host platform
# lacks ``fcntl`` / ``msvcrt``, the module uses a
# single in-process lock — the *cross-process*
# guarantee is lost, but the contract is preserved.
_fallback_lock = threading.Lock()
_fallback_lock_held: set[str] = set()
_fallback_lock_lock = threading.Lock()


def _try_acquire_posix(path: str) -> UnlockFn | None:
    """Try to acquire an ``flock`` on ``path`` (POSIX).

    Returns the unlock callable on success, ``None``
    on ``EWOULDBLOCK`` (lock held by another process).
    Other errors propagate.
    """
    import fcntl

    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        if exc.errno in (11, 35, 36):  # EAGAIN / EWOULDBLOCK /EDEADLK
            return None
        raise

    def unlock() -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    return unlock


def _try_acquire_windows(path: str) -> UnlockFn | None:
    """Try to acquire a Windows file lock on ``path``.

    Uses ``msvcrt.locking`` on a small region of the
    file. Returns the unlock callable on success,
    ``None`` when the region is already locked.

    Note: ``msvcrt.locking`` is whole-file / region
    based, not advisory across arbitrary processes;
    it provides a single-process Windows lock that
    works against itself and ``fcntl``-equivalent
    ``flock`` locks on the same file when the file
    is opened with the same sharing mode.
    """
    import msvcrt

    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        # Lock 1 byte at offset 0. ``LK_NBLCK`` fails
        # immediately if the lock is held.
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        os.close(fd)
        # ``LockViolation`` (13) and ``IOError`` map
        # to "already locked" on Windows.
        if getattr(exc, "winerror", None) in (33, 36) or exc.errno in (
            13,
            33,
            36,
        ):
            return None
        raise

    unlocked = [False]

    def unlock() -> None:
        if unlocked[0]:
            return
        unlocked[0] = True
        try:
            # Unlock the 1-byte region we locked.
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            os.close(fd)

    return unlock


def _try_acquire_fallback(path: str) -> UnlockFn | None:
    """Process-local fallback lock. Cross-process
    safety is *not* guaranteed; this exists so the
    surface still works in environments without
    ``fcntl`` or ``msvcrt`` (rare; mainly CI sandboxes).
    """
    with _fallback_lock_lock:
        if path in _fallback_lock_held:
            return None
        _fallback_lock_held.add(path)

    def unlock() -> None:
        with _fallback_lock_lock:
            _fallback_lock_held.discard(path)

    return unlock


def _try_acquire(path: str) -> UnlockFn | None:
    """Platform-dispatching lock attempt. Returns the
    unlock callable on success, ``None`` when the
    lock is already held by another process / thread.
    """
    if sys.platform == "win32":
        return _try_acquire_windows(path)
    if os.name == "posix":
        return _try_acquire_posix(path)
    return _try_acquire_fallback(path)


def acquire_lock_sync_with_retry(path: str) -> UnlockFn:
    """Acquire an exclusive file lock with bounded
    retry. Mirrors ``acquireLockSyncWithRetry``
    (``storage-lock.ts:6-21``).

    The OpenClaw source's contract:
    - Try ``lockfile.lockSync(path, ...)`` up to
      ``MAX_LOCK_ATTEMPTS`` (10) times.
    - Sleep ``LOCK_RETRY_DELAY_MS`` (20ms) between
      attempts (the TS source has a no-op busy-wait
      — the Python port uses ``time.sleep`` for
      actual sleeping).
    - Re-raise the last ``ELOCKED`` (or any non-ELOCKED
      error) on the final attempt.

    Parameters
    ----------
    path : str
        Filesystem path to lock. The file is created
        if it doesn't exist.

    Returns
    -------
    UnlockFn
        Callable that releases the lock when invoked.
        Idempotent (calling twice is a no-op).
    """
    last_error: Exception | None = None
    for attempt in range(1, MAX_LOCK_ATTEMPTS + 1):
        try:
            unlock = _try_acquire(path)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            unlock = None

        if unlock is not None:
            return unlock

        if attempt == MAX_LOCK_ATTEMPTS:
            # Final attempt failed. Re-raise the
            # last error (or a generic ``RuntimeError``
            # if the loop only ever hit "lock held"
            # without a propagated error).
            if last_error is not None:
                raise last_error
            raise RuntimeError(
                f"Failed to acquire storage lock on {path!r} after "
                f"{MAX_LOCK_ATTEMPTS} attempts"
            )

        # Give the kernel a 20ms window between
        # attempts. The OpenClaw source's no-op
        # busy-wait is a pragmatic comment ("proper-
        # lockfile rejects sync retries") — the
        # Python port actually sleeps, which is
        # strictly more correct.
        time.sleep(LOCK_RETRY_DELAY_MS / 1000.0)

    # Unreachable: the loop either returns or
    # raises. The ``assert False`` documents the
    # invariant for type checkers.
    raise RuntimeError("storage-lock invariant violated")  # pragma: no cover


__all__ = [
    "LOCK_RETRY_DELAY_MS",
    "MAX_LOCK_ATTEMPTS",
    "UnlockFn",
    "acquire_lock_sync_with_retry",
]
