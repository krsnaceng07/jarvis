"""jarvis.config.schema_help — user-facing config field help text facade.

OpenClaw parity: mirrors ``openclaw-main/src/config/schema.help.ts``.

Focused minimal port: aggregates the per-section help tables. Each
``*_FIELD_HELP`` table is exposed as a public constant from a future
port; until those land, only the umbrella ``FIELD_HELP`` is provided.
"""
from __future__ import annotations

from typing import Dict


#: Aggregated user-facing help strings for all config fields.
FIELD_HELP: Dict[str, str] = {}


def get_field_help(field_path: str) -> str:
    """Return the help text for a config field, or empty string if unknown."""
    return FIELD_HELP.get(field_path, "")


__all__ = ["FIELD_HELP", "get_field_help"]
