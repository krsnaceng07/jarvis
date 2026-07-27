"""Persists context-engine runtime quarantines so health surfaces can see
failures recorded in sibling runtime processes.

OpenClaw parity: ``src/context-engine/quarantine-health.ts``. Quarantine
records are camelCase dicts with the runtime-health envelope merged in;
``failedAt`` is exchanged as Unix milliseconds (the TS ``Date`` analogue).
"""
from __future__ import annotations

from typing import Any

from src.plugin_state.runtime_health_store import (
    RuntimeHealthStoreOptions,
    create_runtime_health_record_envelope,
    create_runtime_health_store,
)

__all__ = [
    "clear_persisted_context_engine_quarantine_for_process",
    "list_persisted_context_engine_quarantines",
    "record_persisted_context_engine_quarantine",
]

import json


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _normalize_record(value: dict[str, Any]) -> dict[str, Any] | None:
    if not (
        _is_non_empty_string(value.get("engineId"))
        and _is_non_empty_string(value.get("operation"))
        and _is_non_empty_string(value.get("reason"))
    ):
        return None
    record = {
        "engineId": value["engineId"],
        "operation": value["operation"],
        "reason": value["reason"],
        "failedAtMs": value["failedAtMs"],
        "processId": value["processId"],
        "processToken": value["processToken"],
        "processStartTime": value["processStartTime"],
    }
    if _is_non_empty_string(value.get("owner")):
        record["owner"] = value["owner"]
    return record


# No TTL: a quarantine is recorded once per failure and stays valid for the
# recorder's lifetime, so process liveness alone owns expiry here.
_quarantine_store = create_runtime_health_store(
    RuntimeHealthStoreOptions(
        owner_id="core:context-engine-quarantine-health",
        namespace="runtime-quarantines",
        max_entries=64,
        normalize_record=_normalize_record,
        display_key=lambda record: record["engineId"],
        # Earliest wins, matching the in-memory registry's first-failure-wins
        # rule so health output points at the root cause, not follow-on failures.
        pick="earliest",
    )
)


def _record_key(record: dict[str, Any]) -> str:
    return json.dumps([record["engineId"], record["processId"]], separators=(",", ":"))


def record_persisted_context_engine_quarantine(quarantine: dict[str, Any]) -> None:
    """Persist one quarantine; ``quarantine`` carries ``engineId``, ``owner?``,
    ``operation``, ``reason``, ``failedAtMs``."""
    record: dict[str, Any] = {
        "engineId": quarantine["engineId"],
        "operation": quarantine["operation"],
        "reason": quarantine["reason"],
    }
    record.update(create_runtime_health_record_envelope(quarantine["failedAtMs"]))
    if quarantine.get("owner"):
        record["owner"] = quarantine["owner"]
    # The in-memory registry only records the first quarantine per engine, so
    # this is called at most once per (engine, process) and overwrite is safe.
    _quarantine_store.register(_record_key(record), record)


def list_persisted_context_engine_quarantines() -> list[dict[str, Any]]:
    """One live record per engine id: ``{engineId, owner?, operation, reason, failedAtMs}``."""
    quarantines: list[dict[str, Any]] = []
    for record in _quarantine_store.list():
        quarantine: dict[str, Any] = {
            "engineId": record["engineId"],
            "operation": record["operation"],
            "reason": record["reason"],
            "failedAtMs": record["failedAtMs"],
        }
        if record.get("owner"):
            quarantine["owner"] = record["owner"]
        quarantines.append(quarantine)
    return quarantines


def clear_persisted_context_engine_quarantine_for_process(
    engine_id: str | None, process_id: int
) -> None:
    _quarantine_store.clear_for_process(
        process_id,
        None if engine_id is None else (lambda record: record["engineId"] == engine_id),
    )
