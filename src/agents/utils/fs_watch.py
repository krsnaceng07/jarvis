"""jarvis.agents.utils.fs_watch — filesystem watcher helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/utils/fs-watch.ts``
(35 lines — centralizes retry timing and
close/error handling for agent file watchers).

Public surface (matches the OpenClaw source):

- :data:`FS_WATCH_RETRY_DELAY_MS` — retry delay
  after a watcher error (``fs-watch.ts:8``).
- :func:`close_watcher` — close a watcher,
  swallowing close errors (``fs-watch.ts:10-20``).
- :func:`watch_with_error_handler` — create a
  watcher with an error callback; returns
  ``None`` (and calls ``on_error``) when the
  watch cannot be established
  (``fs-watch.ts:22-35``).

Adaptations
-----------
- Node's ``fs.watch`` has no stdlib equivalent.
  The Python port ships :class:`PollingWatcher`,
  a daemon-thread poller that snapshots the
  watched path (directory listing + per-entry
  mtimes, or a single file's stat) and invokes
  ``listener(event_type, filename)`` with
  ``event_type`` ``"rename"`` (entry appeared /
  disappeared) or ``"change"`` (mtime/size
  moved) — the same two event types Node emits.
  Stat failures on a previously-watchable path
  invoke ``on_error`` once and stop the thread,
  matching the ``watcher.on("error", onError)``
  wiring.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Optional


_LOG = logging.getLogger("jarvis.agents.utils.fs_watch")


#: Retry delay (ms) after a watcher error.
#: Mirrors ``FS_WATCH_RETRY_DELAY_MS``
#: (``fs-watch.ts:8``).
FS_WATCH_RETRY_DELAY_MS: int = 5000

#: Poll interval (seconds) for the Python
#: polling adaptation of ``fs.watch``.
_POLL_INTERVAL_S: float = 0.25


class PollingWatcher:
    """A daemon-thread polling watcher — the
    Python adaptation of Node's ``FSWatcher``.

    Emits ``listener("rename", name)`` when an
    entry appears/disappears and
    ``listener("change", name)`` when an entry's
    mtime or size moves. ``on_error`` fires once
    if the watched path becomes unstatable, then
    the thread stops (parity with the
    ``watcher.on("error", ...)`` wiring).
    """

    def __init__(
        self,
        path: str,
        listener: Callable[[str, Optional[str]], None],
        on_error: Optional[Callable[[], None]] = None,
        poll_interval: float = _POLL_INTERVAL_S,
    ) -> None:
        self._path = path
        self._listener = listener
        self._on_error = on_error
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._is_dir = os.path.isdir(path)
        # Initial snapshot — raises on a broken
        # path so ``watch_with_error_handler``
        # can catch it (parity with fs.watch
        # throwing synchronously).
        self._snapshot = self._take_snapshot()
        self._thread = threading.Thread(
            target=self._run, name=f"fs-watch:{path}", daemon=True
        )
        self._thread.start()

    # ------------------------------------------------------------------

    def close(self) -> None:
        """Stop the watcher thread. Mirrors
        ``FSWatcher.close()``."""
        self._stop.set()

    # ------------------------------------------------------------------

    def _take_snapshot(self) -> dict:
        if self._is_dir:
            snapshot: dict = {}
            for name in os.listdir(self._path):
                try:
                    st = os.stat(os.path.join(self._path, name))
                    snapshot[name] = (st.st_mtime_ns, st.st_size)
                except OSError:
                    snapshot[name] = None
            return snapshot
        st = os.stat(self._path)
        return {None: (st.st_mtime_ns, st.st_size)}

    def _run(self) -> None:
        while not self._stop.wait(self._poll_interval):
            try:
                current = self._take_snapshot()
            except OSError:
                if self._on_error is not None and not self._stop.is_set():
                    try:
                        self._on_error()
                    except Exception:
                        _LOG.exception("fs-watch on_error raised")
                return
            previous = self._snapshot
            self._snapshot = current
            if self._stop.is_set():
                return
            for name in current.keys() - previous.keys():
                self._emit("rename", name)
            for name in previous.keys() - current.keys():
                self._emit("rename", name)
            for name in current.keys() & previous.keys():
                if current[name] != previous[name]:
                    self._emit("change", name)

    def _emit(self, event_type: str, name: Optional[str]) -> None:
        try:
            self._listener(
                event_type,
                name if name is not None else os.path.basename(self._path),
            )
        except Exception:
            _LOG.exception("fs-watch listener raised")


def close_watcher(watcher: Optional[PollingWatcher]) -> None:
    """Close a watcher, swallowing close errors.
    Mirrors :func:`closeWatcher`
    (``fs-watch.ts:10-20``)."""
    if not watcher:
        return
    try:
        watcher.close()
    except Exception:
        # Ignore watcher close errors (ts:17-19).
        pass


def watch_with_error_handler(
    path: str,
    listener: Callable[[str, Optional[str]], None],
    on_error: Callable[[], None],
) -> Optional[PollingWatcher]:
    """Create a watcher with an error callback.
    Mirrors :func:`watchWithErrorHandler`
    (``fs-watch.ts:22-35``): a failed watch
    creation calls ``on_error`` and returns
    ``None``."""
    try:
        return PollingWatcher(path, listener, on_error)
    except Exception:
        on_error()
        return None


__all__ = [
    "FS_WATCH_RETRY_DELAY_MS",
    "PollingWatcher",
    "close_watcher",
    "watch_with_error_handler",
]
