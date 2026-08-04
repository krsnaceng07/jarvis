"""jarvis.config.zod_schema_googlechat — Google Chat channel Zod schema fragments.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.googlechat.ts``.

Focused minimal port: this file in the upstream source is a sibling
fragment to ``zod-schema.providers-googlechat.ts`` and is currently
empty in the OpenClaw main branch (the only export is a placeholder
for the bundled provider schema). The Python port mirrors that by
exposing the same placeholder.
"""
from __future__ import annotations


#: Placeholder for the bundled GoogleChat provider channel schema. The
#: full schema lives in ``zod_schema_providers_googlechat``; this
#: module exists for parity with the upstream directory layout.
GoogleChatChannelSchema = None


__all__ = ["GoogleChatChannelSchema"]
