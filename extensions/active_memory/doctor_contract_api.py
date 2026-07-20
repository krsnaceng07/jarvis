"""doctor_contract_api — doctor state migration for active-memory.

OpenClaw parity: mirrors
``extensions/active-memory/doctor-contract-api.ts``.

Phase 4.2c: the doctor migration that moves legacy
per-session toggle JSON (``<state>/plugins/active-memory/
session-toggles.json``) into the host's plugin-state
keyed store under the ``session-toggles`` namespace.

The migration is idempotent: if the legacy file doesn't
exist, has zero entries, or all entries are already
present in the plugin-state store, the migration is a
no-op. After a successful import, the legacy file is
archived via ``archive_legacy_state_source``.

Surface
-------
- ``resolve_toggle_state_path(state_dir)`` — absolute
  path of the legacy ``session-toggles.json`` file.
- ``active_memory_toggle_key(session_key)`` — SHA-256
  hash of the session key, used as the keyed-store key.
- ``state_migrations`` — list of
  ``PluginDoctorStateMigration`` entries exposed to the
  host's doctor runner. Phase 4.2c ships the
  ``active-memory-session-toggles-json-to-plugin-state``
  migration.

Dependencies
============
- ``extensions.active_memory.types.ActiveMemoryToggleEntry``
- The host provides ``archive_legacy_state_source`` and
  the ``PluginDoctorStateMigration`` type via
  ``jarvis_sdk``.

OpenClaw
-------
The OpenClaw source uses ``crypto.createHash("sha256")``
and the Node ``fs/promises`` API; the Python port uses
``hashlib.sha256`` and the stdlib ``json`` + ``pathlib``
APIs. The key derivation and entry shape are 1:1.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .types import ActiveMemoryToggleEntry

# Module-level constants mirror OpenClaw's:
#   const TOGGLE_STATE_FILE = "session-toggles.json";
#   const SESSION_TOGGLES_NAMESPACE = "session-toggles";
#   const MAX_TOGGLE_ENTRIES = 10_000;
TOGGLE_STATE_FILE = "session-toggles.json"
SESSION_TOGGLES_NAMESPACE = "session-toggles"
MAX_TOGGLE_ENTRIES = 10_000


def resolve_toggle_state_path(state_dir: str | Path) -> str:
    """Return the absolute path of the legacy toggle file.

    Mirrors OpenClaw's ``resolveToggleStatePath``.
    """
    return str(Path(state_dir) / "plugins" / "active-memory" / TOGGLE_STATE_FILE)


def active_memory_toggle_key(session_key: str) -> str:
    """Derive the keyed-store key for a session toggle.

    Mirrors OpenClaw's ``activeMemoryToggleKey`` —
    SHA-256 hash of the session key (UTF-8 encoded),
    returned as a lowercase hex string.
    """
    return hashlib.sha256(session_key.encode("utf-8")).hexdigest()


def _normalize_legacy_updated_at(value: Any) -> int:
    """Coerce a legacy ``updatedAt`` to a finite millisecond timestamp.

    Mirrors OpenClaw's ``normalizeLegacyUpdatedAt`` — falls
    back to ``Date.now()`` (``time.time() * 1000``) for
    non-numeric / NaN / non-finite values.
    """
    import math
    import time

    if isinstance(value, int | float) and not math.isnan(float(value)):
        return int(value)
    return int(time.time() * 1000)


def _read_legacy_toggle_entries(file_path: str) -> list[ActiveMemoryToggleEntry]:
    """Read and parse the legacy ``session-toggles.json`` file.

    Mirrors OpenClaw's ``readLegacyToggleEntries``.
    Returns an empty list on any error (file missing,
    invalid JSON, malformed shape).
    """
    try:
        path = Path(file_path)
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        parsed: Any = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(parsed, dict):
        return []
    sessions = parsed.get("sessions")
    if not isinstance(sessions, dict) or isinstance(sessions, list):
        return []
    entries: list[ActiveMemoryToggleEntry] = []
    for session_key, value in sessions.items():
        if not isinstance(session_key, str) or not session_key.strip():
            continue
        if not isinstance(value, dict) or isinstance(value, list):
            continue
        if value.get("disabled") is not True:
            continue
        entries.append(
            {
                "sessionKey": session_key,
                "disabled": True,
                "updatedAt": _normalize_legacy_updated_at(value.get("updatedAt")),
            }
        )
    return entries


# ── Doctor state migrations ───────────────────────────────────────


def state_migrations() -> list[dict[str, Any]]:
    """Return the list of state migrations to expose to the doctor.

    Mirrors OpenClaw's ``stateMigrations`` export. The
    single migration
    (``active-memory-session-toggles-json-to-plugin-state``)
    reads the legacy JSON file, imports any missing
    entries into the plugin-state keyed store, and
    archives the legacy source on success.
    """
    return [
        {
            "id": "active-memory-session-toggles-json-to-plugin-state",
            "label": "Active Memory session toggles",
            "detectLegacyState": _detect_legacy_toggle_state,
            "migrateLegacyState": _migrate_legacy_toggle_state,
        }
    ]


async def _detect_legacy_toggle_state(params: dict[str, Any]) -> dict[str, Any] | None:
    """Doctor detect step: return a preview if the legacy file has entries."""
    state_dir = params.get("stateDir", "")
    file_path = resolve_toggle_state_path(state_dir)
    entries = _read_legacy_toggle_entries(file_path)
    if not entries:
        return None
    label = "entry" if len(entries) == 1 else "entries"
    return {
        "preview": [
            f"- Active Memory session toggles: {len(entries)} {label} -> "
            f"plugin state ({SESSION_TOGGLES_NAMESPACE})"
        ]
    }


async def _migrate_legacy_toggle_state(params: dict[str, Any]) -> dict[str, Any]:
    """Doctor migrate step: import the legacy file into the keyed store.

    Mirrors OpenClaw's ``migrateLegacyState``. Returns a
    ``{changes, warnings}`` dict. Skips import if the keyed
    store has no room for all missing entries (and leaves
    the legacy file in place).
    """
    import contextlib

    changes: list[str] = []
    warnings: list[str] = []
    state_dir = params.get("stateDir", "")
    file_path = resolve_toggle_state_path(state_dir)
    entries = _read_legacy_toggle_entries(file_path)
    if not entries:
        await _archive_legacy_state_source(
            file_path, "Active Memory session toggles", changes, warnings
        )
        return {"changes": changes, "warnings": warnings}
    context = params.get("context")
    if not isinstance(context, dict):
        return {"changes": changes, "warnings": warnings}
    store_factory = context.get("openPluginStateKeyedStore")
    if not callable(store_factory):
        warnings.append("Skipped Active Memory session toggle migration: keyed store unavailable")
        return {"changes": changes, "warnings": warnings}
    try:
        store = store_factory(
            {
                "namespace": SESSION_TOGGLES_NAMESPACE,
                "maxEntries": MAX_TOGGLE_ENTRIES,
            }
        )
    except Exception as exc:
        warnings.append(f"Skipped Active Memory session toggle migration: {exc}")
        return {"changes": changes, "warnings": warnings}
    try:
        existing = await store.entries()
        existing_keys = {entry.get("key") for entry in existing}
    except Exception:
        existing_keys = set()
    missing = [
        entry
        for entry in entries
        if active_memory_toggle_key(entry["sessionKey"]) not in existing_keys
    ]
    if len(missing) > MAX_TOGGLE_ENTRIES - len(existing_keys):
        warnings.append(
            f"Skipped Active Memory session toggle migration because plugin "
            f"state has room for {MAX_TOGGLE_ENTRIES - len(existing_keys)} "
            f"of {len(missing)} missing entries; left legacy source in place"
        )
        return {"changes": changes, "warnings": warnings}
    imported = 0
    for entry in missing:
        key = active_memory_toggle_key(entry["sessionKey"])
        with contextlib.suppress(Exception):
            await store.register(key, entry)
            imported += 1
    if imported > 0:
        label = "entry" if imported == 1 else "entries"
        changes.append(f"Migrated {imported} Active Memory session toggle {label} -> plugin state")
    await _archive_legacy_state_source(
        file_path, "Active Memory session toggles", changes, warnings
    )
    return {"changes": changes, "warnings": warnings}


async def _archive_legacy_state_source(
    file_path: str,
    label: str,
    changes: list[str],
    warnings: list[str],
) -> None:
    """Best-effort archive of the legacy state file.

    Mirrors OpenClaw's ``archiveLegacyStateSource`` call.
    Falls back to a no-op if the host doesn't expose the
    archive helper.
    """
    import os

    try:
        archive_fn = globals().get("_host_archive_legacy_state_source")
        if callable(archive_fn):
            await archive_fn(  # type: ignore[misc]
                {
                    "filePath": file_path,
                    "label": label,
                    "changes": changes,
                    "warnings": warnings,
                }
            )
            return
    except Exception:  # noqa: S110 — best-effort archive
        pass
    # Default fallback: delete the file. The host can
    # override ``_host_archive_legacy_state_source`` via
    # the doctor runner to route to a richer archive flow.
    try:
        os.remove(file_path)
        changes.append(f"Archived {label} legacy source: {file_path}")
    except FileNotFoundError:
        pass
    except OSError as exc:
        warnings.append(f"Failed to archive {label} legacy source: {exc}")


__all__ = [
    "MAX_TOGGLE_ENTRIES",
    "SESSION_TOGGLES_NAMESPACE",
    "TOGGLE_STATE_FILE",
    "active_memory_toggle_key",
    "resolve_toggle_state_path",
    "state_migrations",
]
