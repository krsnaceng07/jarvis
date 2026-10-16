"""Version and package pins for the managed Codex app-server runtime.

OpenClaw parity: ``extensions/codex/src/app-server/version.ts``.
"""

from __future__ import annotations

#: Exact Codex app-server version shipped by the JARVIS Codex bridge.
CODEX_APP_SERVER_VERSION: str = "0.153.4"

#: Inclusive runtime compatibility floor for external app-server binaries.
MIN_SUPPORTED_CODEX_APP_SERVER_VERSION: str = "0.149.0"

#: npm package name for the managed Codex app-server binary.
MANAGED_CODEX_APP_SERVER_PACKAGE: str = "@openai/codex"

__all__ = [
    "CODEX_APP_SERVER_VERSION",
    "MANAGED_CODEX_APP_SERVER_PACKAGE",
    "MIN_SUPPORTED_CODEX_APP_SERVER_VERSION",
]
