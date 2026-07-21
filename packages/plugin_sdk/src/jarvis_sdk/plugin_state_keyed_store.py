"""jarvis_sdk.plugin_state_keyed_store — OpenClaw-shaped keyed store.

OpenClaw parity: mirrors
``openclaw/plugin-sdk/plugin-state-runtime``'s
``OpenKeyedStoreOptions`` / ``PluginStateKeyedStore``
contracts from
``src/plugin-state/plugin-state-store.types.ts``.

Used by ``memory-wiki`` state stores
(``source-sync-state``, ``import-runs-state``,
``compiled-cache``). Each state store opens its
own namespace and persists JSON-compatible
records under a process-local directory.

Architecture
============
The Python port is a single-file
``PluginStateKeyedStore`` that wraps the
existing :class:`KeyedStore` file-backed store
and exposes the OpenClaw-shaped API:

- ``register(key, value, *, ttl_ms=None)`` --
  upsert; raises if ``overflowPolicy="reject-new"``
  and the namespace is full.
- ``register_if_absent(key, value, ...)`` --
  upsert only if the key is currently missing.
- ``lookup(key)`` -- read a single entry; returns
  ``None`` if the key is missing.
- ``delete(key)`` -- remove an entry; returns
  whether the key existed.
- ``entries()`` -- list every entry as
  ``PluginStateEntry`` dataclass (key + value +
  createdAt + optional expiresAt).
- ``clear()`` -- drop every entry.

Backed by the file-backed
:class:`KeyedStore` for cross-process
durability; an in-memory fallback is used when
the underlying store isn't configured (so the
plugin can still operate in test mode).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from .plugin_state import (
    KeyedStore,
    OpenKeyedStoreOptions as _FileBackedOpenKeyedStoreOptions,
    open_keyed_store,
)

if TYPE_CHECKING:
    from pathlib import Path

_T = TypeVar("_T")


# Default namespace root. The host sets this via
# ``set_plugin_state_namespace_root``; absent
# configuration, the store falls back to an
# in-memory implementation (so tests can run
# without a temp dir).
_DEFAULT_NAMESPACE_ROOT: Path | None = None


def set_plugin_state_namespace_root(root: Path | None) -> None:
    """Configure the process-wide namespace root for keyed stores.

    Mirrors how the OpenClaw runtime points
    the keyed store at
    ``$OPENCLAW_STATE_DIR``. The Python port
    defaults to in-memory storage; tests can
    opt into a temp dir.
    """
    global _DEFAULT_NAMESPACE_ROOT  # noqa: PLW0603 — process-wide SDK config
    _DEFAULT_NAMESPACE_ROOT = root


def get_plugin_state_namespace_root() -> Path | None:
    """Return the current namespace root (``None`` → in-memory fallback)."""
    return _DEFAULT_NAMESPACE_ROOT


@dataclass(frozen=True, slots=True)
class OpenKeyedStoreOptions:
    """Per-store configuration. Mirrors OpenClaw's options struct.

    ``namespace`` is the subdirectory under the
    process-wide root (e.g. ``"memory-wiki-source-sync"``).
    ``max_entries`` enforces a per-namespace cap.
    ``overflow_policy`` controls what happens
    when the cap is exceeded:

    - ``"evict-oldest"`` (default) drops the
      oldest entry.
    - ``"reject-new"`` raises
      :class:`PluginStateStoreError`.
    """

    namespace: str
    max_entries: int
    overflow_policy: str = "evict-oldest"
    default_ttl_ms: int | None = None


@dataclass(frozen=True, slots=True)
class PluginStateEntry(Generic[_T]):
    """Mirrors OpenClaw's ``PluginStateEntry<T>``.

    ``created_at`` is the Unix-ms timestamp of
    the first registration. ``expires_at`` is
    the optional Unix-ms timestamp when the
    entry should be considered stale; the
    store filters expired entries on lookup /
    entries.
    """

    key: str
    value: _T
    created_at: int
    expires_at: int | None = None


class PluginStateStoreError(RuntimeError):
    """Raised for plugin-state validation + capacity failures."""


class _InMemoryKeyedStore(Generic[_T]):
    """In-memory fallback used when no namespace root is configured.

    Mirrors the surface of the file-backed
    store so callers can be unaware of the
    backing implementation. Used for tests and
    for the memory-wiki compile-time pass that
    doesn't need cross-process durability.
    """

    def __init__(self, options: OpenKeyedStoreOptions) -> None:
        self._options = options
        self._entries: dict[str, PluginStateEntry[_T]] = {}

    def _expired(self, entry: PluginStateEntry[_T]) -> bool:
        if entry.expires_at is None:
            return False
        return int(time.time() * 1000) >= entry.expires_at

    def _evict_if_full(self) -> None:
        if len(self._entries) < self._options.max_entries:
            return
        if self._options.overflow_policy == "reject-new":
            raise PluginStateStoreError(
                f"Plugin state namespace {self._options.namespace!r} is full "
                f"({self._options.max_entries} entries)"
            )
        # evict-oldest: drop the entry with the
        # smallest createdAt.
        oldest_key = min(self._entries, key=lambda k: self._entries[k].created_at)
        self._entries.pop(oldest_key, None)

    def register(
        self,
        key: str,
        value: _T,
        *,
        ttl_ms: int | None = None,
    ) -> None:
        self._evict_if_full()
        now_ms = int(time.time() * 1000)
        expires = (
            now_ms + ttl_ms
            if ttl_ms is not None
            else (
                now_ms + self._options.default_ttl_ms
                if self._options.default_ttl_ms is not None
                else None
            )
        )
        self._entries[key] = PluginStateEntry(
            key=key,
            value=value,
            created_at=now_ms,
            expires_at=expires,
        )

    def register_if_absent(
        self,
        key: str,
        value: _T,
        *,
        ttl_ms: int | None = None,
    ) -> bool:
        if key in self._entries and not self._expired(self._entries[key]):
            return False
        self.register(key, value, ttl_ms=ttl_ms)
        return True

    def lookup(self, key: str) -> _T | None:
        entry = self._entries.get(key)
        if entry is None or self._expired(entry):
            return None
        return entry.value

    def delete(self, key: str) -> bool:
        return self._entries.pop(key, None) is not None

    def entries(self) -> list[PluginStateEntry[_T]]:
        return [entry for entry in self._entries.values() if not self._expired(entry)]

    def clear(self) -> None:
        self._entries.clear()


class PluginStateKeyedStore(Generic[_T]):
    """The OpenClaw-shaped keyed store.

    Wraps an underlying implementation
    (in-memory by default; file-backed when a
    namespace root is configured). The wrapper
    normalizes the API to the OpenClaw contract.
    """

    def __init__(self, options: OpenKeyedStoreOptions) -> None:
        self._options = options
        root = get_plugin_state_namespace_root()
        self._in_memory: _InMemoryKeyedStore[_T] | None = None
        self._file_store: KeyedStore | None = None
        if root is None:
            self._in_memory = _InMemoryKeyedStore(options)
        else:
            self._file_store = open_keyed_store(
                _FileBackedOpenKeyedStoreOptions(
                    root=root,
                    name=options.namespace,
                )
            )

    def _read_entry(self, key: str) -> PluginStateEntry[_T] | None:
        if self._in_memory is not None:
            return self._in_memory._entries.get(key)
        assert self._file_store is not None
        data = self._file_store.read(key)
        if data is None:
            return None
        return _entry_from_dict(key, data)

    def register(
        self,
        key: str,
        value: _T,
        *,
        ttl_ms: int | None = None,
    ) -> None:
        if self._in_memory is not None:
            self._in_memory.register(key, value, ttl_ms=ttl_ms)
            return
        assert self._file_store is not None
        # File-backed path: store the full
        # PluginStateEntry shape so the lookup /
        # entries round-trip preserves
        # createdAt + expiresAt.
        existing = self._read_entry(key)
        now_ms = int(time.time() * 1000)
        if existing is None and self._options.overflow_policy == "reject-new":
            # Cap check: count existing files.
            existing_keys = set(self._file_store.list_keys())
            if len(existing_keys) >= self._options.max_entries:
                raise PluginStateStoreError(
                    f"Plugin state namespace {self._options.namespace!r} is full "
                    f"({self._options.max_entries} entries)"
                )
        created_at = existing.created_at if existing is not None else now_ms
        if ttl_ms is not None:
            expires_at: int | None = now_ms + ttl_ms
        elif self._options.default_ttl_ms is not None:
            expires_at = now_ms + self._options.default_ttl_ms
        else:
            expires_at = existing.expires_at if existing is not None else None
        payload: dict[str, Any] = {
            "value": value,
            "createdAt": created_at,
        }
        if expires_at is not None:
            payload["expiresAt"] = expires_at
        self._file_store.write(key, payload)
        # Cap check for evict-oldest: count + drop
        # the oldest if necessary.
        if self._options.overflow_policy == "evict-oldest":
            keys = self._file_store.list_keys()
            if len(keys) > self._options.max_entries:
                # Drop the oldest by createdAt.
                entries = [(k, self._read_entry(k)) for k in keys if k != key]
                entries = [(k, e) for k, e in entries if e is not None]
                if entries:
                    entries.sort(key=lambda pair: pair[1].created_at)  # type: ignore[union-attr]
                    self._file_store.delete(entries[0][0])

    def register_if_absent(
        self,
        key: str,
        value: _T,
        *,
        ttl_ms: int | None = None,
    ) -> bool:
        if self.lookup(key) is not None:
            return False
        self.register(key, value, ttl_ms=ttl_ms)
        return True

    def lookup(self, key: str) -> _T | None:
        entry = self._read_entry(key)
        if entry is None:
            return None
        if entry.expires_at is not None and int(time.time() * 1000) >= entry.expires_at:
            return None
        return entry.value

    def delete(self, key: str) -> bool:
        if self._in_memory is not None:
            return self._in_memory.delete(key)
        assert self._file_store is not None
        return self._file_store.delete(key)

    def entries(self) -> list[PluginStateEntry[_T]]:
        if self._in_memory is not None:
            return self._in_memory.entries()
        assert self._file_store is not None
        now_ms = int(time.time() * 1000)
        out: list[PluginStateEntry[_T]] = []
        for key in self._file_store.list_keys():
            entry = self._read_entry(key)
            if entry is None:
                continue
            if entry.expires_at is not None and now_ms >= entry.expires_at:
                continue
            out.append(entry)
        return out

    def clear(self) -> None:
        if self._in_memory is not None:
            self._in_memory.clear()
            return
        assert self._file_store is not None
        for key in self._file_store.list_keys():
            self._file_store.delete(key)


def _entry_from_dict(
    key: str,
    data: dict[str, Any],
) -> PluginStateEntry[Any] | None:
    """Build a ``PluginStateEntry`` from a stored JSON dict."""
    value: Any = data.get("value")
    created_at_raw = data.get("createdAt")
    if not isinstance(created_at_raw, int | float):
        return None
    expires_at_raw = data.get("expiresAt")
    expires_at: int | None = None
    if isinstance(expires_at_raw, int | float):
        expires_at = int(expires_at_raw)
    return PluginStateEntry(
        key=key,
        value=value,
        created_at=int(created_at_raw),
        expires_at=expires_at,
    )


def open_plugin_state_keyed_store(
    options: OpenKeyedStoreOptions,
) -> PluginStateKeyedStore[Any]:
    """Open a keyed store with the OpenClaw contract.

    Mirrors ``openclaw/plugin-sdk/plugin-state-runtime``'s
    ``openKeyedStore``. The store type is
    :class:`PluginStateKeyedStore` and the value
    type is the caller's responsibility.
    """
    return PluginStateKeyedStore(options)


def reset_plugin_state_for_tests() -> None:
    """Reset the namespace root (test-only helper).

    Clears the process-wide namespace root so
    subsequent tests start from a clean slate.
    Production code MUST NOT call this.
    """
    set_plugin_state_namespace_root(None)


__all__ = [
    "OpenKeyedStoreOptions",
    "PluginStateEntry",
    "PluginStateKeyedStore",
    "PluginStateStoreError",
    "get_plugin_state_namespace_root",
    "open_plugin_state_keyed_store",
    "reset_plugin_state_for_tests",
    "set_plugin_state_namespace_root",
]
