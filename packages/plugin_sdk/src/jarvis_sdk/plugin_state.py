"""jarvis_sdk.plugin_state — keyed store + lease pattern.

OpenClaw parity: mirrors
``openclaw/plugin-sdk/plugin-state-runtime``'s
``OpenKeyedStoreOptions``, ``PluginStateLeaseRunner``, and
``openKeyedStore``.

Used by ``memory-core``'s dreaming subsystem (state
persistence for light/REM/deep sweep progress) and
``memory-wiki`` (compiled cache owner identity, source sync
state, import run state).

Architecture
============
OpenClaw's state layer is a per-key file-backed store
with a per-key lease (a write lock that expires after a
timeout so a crashed plugin can't deadlock the store). The
Python port uses a per-key JSON file with a ``.lock`` file
for the lease.

The lease is acquired by creating ``<key>.lock`` with a
timestamp; the lease is considered held if the timestamp is
within ``lease_ms``. On expiry, the next writer steals the
lease.

Parity
======
- ``open_keyed_store(options)`` → ``KeyedStore``
- ``KeyedStore.read(key)`` → ``dict | None``
- ``KeyedStore.write(key, data)`` → ``None``
- ``with_lease(store, key, fn)`` → ``T``: runs ``fn``
  inside a lease; raises ``LeaseHeld`` if another writer
  currently holds the lock.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from pathlib import Path

_T = TypeVar("_T")


class LeaseHeld(RuntimeError):
    """Raised when another writer holds the lease for a key."""


@dataclass(frozen=True, slots=True)
class OpenKeyedStoreOptions:
    """Per-store configuration. Mirrors OpenClaw's options struct."""

    root: Path
    name: str  # subdir under root (e.g. "memory-core-dreaming")
    lease_ms: int = 30_000


class KeyedStore:
    """Per-key file-backed store with a per-key lease.

    Mirrors ``openclaw/plugin-sdk/plugin-state-runtime``'s
    ``openKeyedStore``. Each key is a JSON file under
    ``<root>/<name>/<key>.json``. Locks live at
    ``<root>/<name>/<key>.lock`` and carry a timestamp.
    """

    def __init__(self, options: OpenKeyedStoreOptions) -> None:
        self._root = options.root / options.name
        self._lease_ms = options.lease_ms
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key or "/" in key or "\\" in key or ".." in key:
            raise ValueError(f"invalid key: {key!r}")
        return self._root / f"{key}.json"

    def _lock_path(self, key: str) -> Path:
        return self._root / f"{key}.lock"

    def read(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def write(self, key: str, data: dict[str, Any]) -> None:
        """Atomically write ``data`` to ``<root>/<name>/<key>.json``."""
        path = self._path(key)
        tmp = path.with_suffix(f".json.{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except Exception:
            with contextlib.suppress(OSError):
                tmp.unlink()
            raise

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_keys(self) -> list[str]:
        return [p.stem for p in self._root.glob("*.json") if p.is_file()]

    def acquire_lease(self, key: str) -> str | None:
        """Try to acquire the lease. Returns the lock token on success."""
        lock_path = self._lock_path(key)
        token = uuid.uuid4().hex
        now_ms = int(time.time() * 1000)
        # Atomic create: O_CREAT | O_EXCL semantics via open with "x" mode.
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, f"{token}\n{now_ms}\n".encode())
            finally:
                os.close(fd)
            return token
        except FileExistsError:
            # Check if the existing lock is stale.
            try:
                content = lock_path.read_text(encoding="utf-8").splitlines()
                existing_token = content[0] if content else ""
                lock_ts_ms = int(content[1]) if len(content) > 1 else 0
            except (OSError, ValueError, IndexError):
                return None
            if now_ms - lock_ts_ms > self._lease_ms:
                # Stale: try to steal by unlinking + recreating.
                try:
                    lock_path.unlink()
                    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    try:
                        os.write(fd, f"{token}\n{now_ms}\n".encode())
                    finally:
                        os.close(fd)
                    return token
                except (FileExistsError, OSError):
                    return None
            # Active lease held by another token; existing_token is for
            # debug only (we don't need to verify it).
            _ = existing_token
            return None

    def release_lease(self, key: str, token: str) -> bool:
        lock_path = self._lock_path(key)
        if not lock_path.exists():
            return False
        try:
            content = lock_path.read_text(encoding="utf-8").splitlines()
            if content and content[0] == token:
                lock_path.unlink()
                return True
        except (OSError, ValueError, IndexError):
            return False
        return False


def open_keyed_store(options: OpenKeyedStoreOptions) -> KeyedStore:
    """Mirror OpenClaw's ``openKeyedStore(options)`` factory."""
    return KeyedStore(options)


@contextmanager
def with_lease(store: KeyedStore, key: str):
    """Context manager that runs the body inside a lease.

    Mirrors OpenClaw's ``PluginStateLeaseRunner.withLease``.
    Raises ``LeaseHeld`` if another writer holds the lease.
    """
    token = store.acquire_lease(key)
    if token is None:
        raise LeaseHeld(f"lease for key {key!r} is currently held")
    try:
        yield token
    finally:
        store.release_lease(key, token)


__all__ = [
    "KeyedStore",
    "LeaseHeld",
    "OpenKeyedStoreOptions",
    "open_keyed_store",
    "with_lease",
]
