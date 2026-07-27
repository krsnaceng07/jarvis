"""Exclusive plugin slot defaults and helpers.

OpenClaw parity: ``src/plugins/slots.ts``. Only the default-id lookup is
ported for the context-engine slice; the exclusive-selection helpers land
with the plugin-slot phase.
"""
from __future__ import annotations

__all__ = ["DEFAULT_SLOT_BY_KEY", "default_slot_id_for_key"]

DEFAULT_SLOT_BY_KEY: dict[str, str] = {
    "memory": "memory-core",
    "contextEngine": "legacy",
}


def default_slot_id_for_key(slot_key: str) -> str:
    """Return the built-in default engine id for an exclusive slot key."""
    default_id = DEFAULT_SLOT_BY_KEY.get(slot_key)
    if default_id is None:
        raise KeyError(f"Unknown exclusive plugin slot key: {slot_key!r}")
    return default_id
