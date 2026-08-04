"""jarvis.shared.json_schema_types — JSON schema shared type aliases.

OpenClaw parity: mirrors ``openclaw-main/src/shared/json-schema.types.ts``.
"""
from __future__ import annotations

from typing import Any, Dict


#: Generic JSON-schema object alias (mirrors TypeBox's TSchema).
JsonSchemaObject = Dict[str, Any]


__all__ = ["JsonSchemaObject"]
