"""jarvis.routing — Tiered route resolution.

OpenClaw parity: mirrors ``src/routing/`` (resolve-route.ts +
session-key.ts + 9 smaller files).

Re-export shim: a follow-up phase will physically move
``jarvis_sdk.routing`` here and update all import sites.
"""
from __future__ import annotations

from jarvis_sdk.routing import (  # noqa: F401
    normalize_agent_id,
    parse_agent_session_key,
    parse_thread_session_suffix,
)

__all__ = [
    "normalize_agent_id",
    "parse_agent_session_key",
    "parse_thread_session_suffix",
]
