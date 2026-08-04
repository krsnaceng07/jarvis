"""jarvis.config.zod_schema_providers_googlechat — Google Chat provider Zod schemas.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.providers-googlechat.ts``.
"""
from __future__ import annotations

from typing import Any


#: GoogleChat account-level Zod schema.
GoogleChatAccountSchema: Any = None  # z.object({...}).strict()

#: GoogleChat top-level Zod config schema.
GoogleChatConfigSchema: Any = None  # GoogleChatAccountSchema.extend({...})


__all__ = [
    "GoogleChatAccountSchema",
    "GoogleChatConfigSchema",
]
