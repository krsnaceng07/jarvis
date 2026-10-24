"""Legacy context engine wraps pre-plugin context behavior behind the pluggable interface.

OpenClaw parity: ``src/context-engine/legacy.ts``.

- ingest: no-op (SessionManager handles message persistence)
- assemble: pass-through (existing sanitize/validate/limit pipeline handles this)
- compact: delegates to the built-in runtime compaction path
"""
from __future__ import annotations

from typing import Any

from .delegate import delegate_compaction_to_runtime

__all__ = ["LegacyContextEngine", "create_legacy_context_engine"]


def create_legacy_context_engine() -> LegacyContextEngine:
    """Factory creating a new LegacyContextEngine instance."""
    return LegacyContextEngine()


class LegacyContextEngine:
    """Preserves 100% backward compatibility behind the ContextEngine contract."""

    info: dict[str, Any] = {
        "id": "legacy",
        "name": "Legacy Context Engine",
        "version": "1.0.0",
    }

    async def ingest(self, params: dict[str, Any]) -> dict[str, Any]:
        # No-op: SessionManager handles message persistence in the legacy flow
        return {"ingested": False}

    async def assemble(self, params: dict[str, Any]) -> dict[str, Any]:
        # Pass-through: the existing sanitize -> validate -> limit -> repair
        # pipeline handles context assembly for the legacy engine. We just
        # return the messages as-is with a rough token estimate.
        return {
            "messages": params["messages"],
            "estimatedTokens": 0,  # Caller handles estimation
        }

    async def afterTurn(self, params: dict[str, Any]) -> None:  # noqa: N802 — wire name
        # No-op: legacy flow persists context directly in SessionManager.
        return None

    async def compact(self, params: dict[str, Any]) -> dict[str, Any]:
        return await delegate_compaction_to_runtime(params)

    async def dispose(self) -> None:
        # Nothing to clean up for legacy engine
        return None
