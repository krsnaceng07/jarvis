"""lancedb_runtime — lazy loader for the ``lancedb`` module.

OpenClaw parity: mirrors ``extensions/memory-lancedb/lancedb-runtime.ts``.

The LanceDB native module is heavy and may not be installable
on every platform (e.g. some Windows + Python combinations).
We follow OpenClaw's pattern: a module-level lazy loader that
caches the import on success, retries on failure, and surfaces
a clean error if the runtime can't be loaded.

For tests and for environments where LanceDB isn't installed,
we expose a small in-memory vector store implementation that
plugs into the same ``MemoryStore`` protocol as the real
LanceDB backend.
"""

from __future__ import annotations

import importlib
import logging
import struct
import sys
import threading
from typing import Any, Protocol

_log = logging.getLogger("extensions.memory_lancedb")


class LanceDbModule(Protocol):
    """Type stub for the subset of ``lancedb`` we use.

    Mirrors the type imports in OpenClaw's
    ``lancedb-runtime.ts``. We keep this loose so test doubles
    can satisfy the protocol.
    """

    def connect(self, path: str, **opts: Any) -> Any: ...


class _LoaderState:
    """Mutable loader state.

    Mirrors the closure shape of OpenClaw's
    ``createLanceDbRuntimeLoader``. We expose a single shared
    loader by default but tests can swap the underlying
    ``import_module`` to inject a fake.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cached: LanceDbModule | None = None
        self._failed: BaseException | None = None


_state = _LoaderState()


def _default_import() -> LanceDbModule:
    """Default loader: ``importlib.import_module("lancedb")``."""
    return importlib.import_module("lancedb")  # type: ignore[return-value]


def is_lancedb_available() -> bool:
    """Return True if the ``lancedb`` module imports successfully.

    Safe to call repeatedly; the result is cached.
    """
    if _state._cached is not None:
        return True
    try:
        _state._cached = _default_import()
    except Exception as exc:
        _state._failed = exc
        return False
    return True


def load_lancedb_module(
    *,
    import_module: Any = None,
) -> LanceDbModule:
    """Return the ``lancedb`` module, importing it on first call.

    Mirrors OpenClaw's ``loadLanceDbModule``. The result is
    cached so subsequent calls are O(1). On failure the cache
    is invalidated so the next call can retry (e.g. after the
    operator installs the dep).
    """
    import_fn = import_module or _default_import
    if _state._cached is not None:
        return _state._cached
    with _state._lock:
        if _state._cached is not None:
            return _state._cached
        try:
            module = import_fn()
        except Exception as exc:
            _state._failed = exc
            _log.debug("lancedb import failed: %s", exc)
            raise RuntimeError(
                "memory-lancedb: bundled lancedb dependency is unavailable. "
                "Install or repair the memory-lancedb plugin package "
                "dependencies, then restart JARVIS."
            ) from exc
        _state._cached = module
        return module


def reset_loader_for_tests() -> None:
    """Reset the cached loader. Tests use this to force a reload."""
    with _state._lock:
        _state._cached = None
        _state._failed = None


def detect_native_platform() -> tuple[str, str]:
    """Return ``(platform, arch)`` for the current Python runtime.

    Mirrors ``process.platform`` / ``process.arch`` from
    OpenClaw. Used by the doctor contract to warn about
    unsupported native combinations.
    """
    plat = sys.platform
    arch = _resolve_arch()
    return plat, arch


def _resolve_arch() -> str:
    """Best-effort architecture detection without importing platform."""
    # 64-bit Windows reports 8; 64-bit Linux/macOS reports 8; 32-bit reports 4.
    try:
        bits = struct.calcsize("P") * 8
    except Exception:
        return "unknown"
    return {8: "x64", 4: "x86"}.get(bits, f"{bits}bit")


__all__ = [
    "LanceDbModule",
    "detect_native_platform",
    "is_lancedb_available",
    "load_lancedb_module",
    "reset_loader_for_tests",
]
