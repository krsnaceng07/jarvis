"""jarvis.config.zod_schema_providers_whatsapp — WhatsApp provider Zod schema.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.providers-whatsapp.ts``.

Focused minimal port: thin facade.
"""
from __future__ import annotations

from typing import Any


#: WhatsApp account-level Zod schema.
WhatsAppAccountSchema: Any = None  # z.object({...}).strict()

#: WhatsApp top-level Zod config schema.
WhatsAppConfigSchema: Any = None  # WhatsAppAccountSchema.extend({...})


__all__ = [
    "WhatsAppAccountSchema",
    "WhatsAppConfigSchema",
]
