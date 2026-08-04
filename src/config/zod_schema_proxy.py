"""jarvis.config.zod_schema_proxy — proxy-related Zod schema fragments.

OpenClaw parity: mirrors ``openclaw-main/src/config/zod-schema.proxy.ts``.

Focused minimal port: schema definitions exposed as Python type stubs.
"""
from __future__ import annotations

from typing import Any


#: Proxy config schema (zod).
ProxyConfigSchema: Any = None


#: Loopback handling modes.
ProxyLoopbackModeSchema: Any = None  # z.enum(["gateway-only", "proxy", "block"])


#: TLS settings for proxy transport.
ProxyTlsConfigSchema: Any = None


__all__ = [
    "ProxyConfigSchema",
    "ProxyLoopbackModeSchema",
    "ProxyTlsConfigSchema",
]
