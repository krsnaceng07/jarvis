"""jarvis.routing — Tiered route resolution.

OpenClaw parity: mirrors ``src/routing/`` (resolve-route.ts +
session-key.ts + 9 smaller files).
"""
from __future__ import annotations

from .routing import (  # noqa: F401
    normalize_agent_id,
    parse_agent_session_key,
    parse_thread_session_suffix,
)

__all__ = [
    "normalize_agent_id",
    "parse_agent_session_key",
    "parse_thread_session_suffix",
]
