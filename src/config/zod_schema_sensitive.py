"""jarvis.config.zod_schema_sensitive — sensitive config schema fragment registry.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.sensitive.ts``.

Focused minimal port: exposes the registry placeholder. The real zod
registry lands with the schema validator port.
"""
from __future__ import annotations

from typing import Any


#: Marker registry for redaction-aware schemas. zod.registry<undefined, z.ZodType>()
sensitive: Any = None


__all__ = ["sensitive"]
