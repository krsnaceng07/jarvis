"""Cross-process runtime health records persisted in the plugin-state store.

OpenClaw parity: ``src/plugin-state/runtime-health-store.ts`` — envelope
validation, process-liveness hygiene, and per-process cleanup. Domain
modules own record fields and display keys.

Records surface only with a positive incarnation match; unverifiable
identity fails closed so a recycled PID can never keep stale failures
alive. Own PID: the per-process token proves incarnation on every
platform. Sibling PIDs: the Linux ``/proc`` starttime must match; where
it is unavailable (non-Linux, ``/proc`` read failure) sibling visibility
is sacrificed instead of trusting a bare ``kill(0)`` liveness probe.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

from jarvis_sdk.plugin_state_keyed_store import (
    OpenKeyedStoreOptions,
    PluginStateKeyedStore,
    open_plugin_state_keyed_store,
)

from src.shared.pid_alive import get_process_start_time

__all__ = [
    "RuntimeHealthRecordEnvelope",
    "RuntimeHealthStore",
    "RuntimeHealthStoreOptions",
    "create_runtime_health_record_envelope",
    "create_runtime_health_store",
    "current_process_token",
]

_T = TypeVar("_T")

# One token per process lifetime: a restarted process (even with a recycled
# PID) can never match records written by its predecessor.
_CURRENT_PROCESS_TOKEN = str(uuid.uuid4())


def current_process_token() -> str:
    """Random per-process identity token (test hooks read it)."""
    return _CURRENT_PROCESS_TOKEN


@dataclass(frozen=True)
class RuntimeHealthRecordEnvelope:
    """Envelope persisted with every cross-process runtime health record."""

    process_id: int
    process_token: str
    process_start_time: int | None
    failed_at_ms: float


@dataclass(frozen=True)
class RuntimeHealthStoreOptions(Generic[_T]):
    """Configuration for one health-record namespace.

    ``normalize_record`` validates domain fields and strips unknown ones
    (the envelope is pre-validated). ``display_key`` groups records for
    display dedupe across recorder processes. ``pick`` chooses which
    ``failed_at_ms`` wins per display group: ``"earliest"`` (root cause)
    or ``"latest"`` (most recent reason).
    """

    owner_id: str
    namespace: str
    max_entries: int
    normalize_record: Callable[[dict[str, Any]], _T | None]
    display_key: Callable[[_T], str]
    pick: str  # "earliest" | "latest"
    ttl_ms: int | None = None


def _has_valid_envelope(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    process_id = value.get("processId")
    process_token = value.get("processToken")
    process_start_time = value.get("processStartTime")
    failed_at_ms = value.get("failedAtMs")
    if not (isinstance(process_id, int) and not isinstance(process_id, bool) and process_id > 0):
        return False
    if not (isinstance(process_token, str) and process_token):
        return False
    if process_start_time is not None and not (
        isinstance(process_start_time, (int, float))
        and not isinstance(process_start_time, bool)
        and process_start_time >= 0
    ):
        return False
    return isinstance(failed_at_ms, (int, float)) and not isinstance(failed_at_ms, bool)


def create_runtime_health_record_envelope(failed_at_ms: float) -> dict[str, Any]:
    """Build the common health envelope for records owned by this process.

    Returns the wire (camelCase) dict merged into domain records, matching
    OpenClaw's ``createRuntimeHealthRecordEnvelope`` (which takes a Date;
    the Python port takes Unix milliseconds directly).
    """
    return {
        "processId": os.getpid(),
        "processToken": _CURRENT_PROCESS_TOKEN,
        "processStartTime": get_process_start_time(os.getpid()),
        "failedAtMs": failed_at_ms,
    }


def _process_looks_live(record: dict[str, Any]) -> bool:
    if record["processId"] == os.getpid():
        return record["processToken"] == _CURRENT_PROCESS_TOKEN
    current_start_time = get_process_start_time(record["processId"])
    return current_start_time is not None and current_start_time == record["processStartTime"]


class RuntimeHealthStore(Generic[_T]):
    """SQLite/file-backed health record namespace shared across processes."""

    def __init__(self, options: RuntimeHealthStoreOptions[_T]) -> None:
        self._options = options

    def _open_store(self) -> PluginStateKeyedStore[Any]:
        # Opened per operation so records follow the state dir active at
        # call time (tests and embedded runtimes swap the namespace root).
        return open_plugin_state_keyed_store(
            OpenKeyedStoreOptions(
                namespace=self._options.namespace,
                max_entries=self._options.max_entries,
                default_ttl_ms=self._options.ttl_ms,
            )
        )

    def _normalize(self, value: Any) -> _T | None:
        if not _has_valid_envelope(value):
            return None
        return self._options.normalize_record(value)

    def register(self, key: str, record: dict[str, Any]) -> None:
        """Persist a record under ``key``, overwriting any prior value."""
        self._open_store().register(key, record)

    def list(self) -> list[_T]:
        """One record per display group, restricted to live recorder processes."""
        try:
            by_group: dict[str, tuple[_T, float]] = {}
            for entry in self._open_store().entries():
                raw = entry.value
                record = self._normalize(raw)
                if record is None or not _process_looks_live(raw):
                    continue
                group_key = self._options.display_key(record)
                failed_at_ms = float(raw["failedAtMs"])
                existing = by_group.get(group_key)
                wins = existing is None or (
                    failed_at_ms > existing[1]
                    if self._options.pick == "latest"
                    else failed_at_ms < existing[1]
                )
                if wins:
                    by_group[group_key] = (record, failed_at_ms)
            return [record for record, _ in by_group.values()]
        except Exception:
            return []

    def clear_for_process(
        self,
        process_id: int,
        matches: Callable[[_T], bool] | None = None,
    ) -> None:
        """Remove records recorded by the process, optionally narrowed."""
        try:
            store = self._open_store()
            for entry in store.entries():
                raw = entry.value
                record = self._normalize(raw)
                if record is None:
                    continue
                if raw["processId"] == process_id and (matches is None or matches(record)):
                    store.delete(entry.key)
        except Exception:
            # Best-effort cleanup; callers also clear their in-memory state.
            pass


def create_runtime_health_store(
    options: RuntimeHealthStoreOptions[_T],
) -> RuntimeHealthStore[_T]:
    """Open a health record namespace shared across runtime processes."""
    return RuntimeHealthStore(options)
