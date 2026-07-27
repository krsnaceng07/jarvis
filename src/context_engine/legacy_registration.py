"""Legacy context-engine registration installs the built-in fallback under core ownership.

OpenClaw parity: ``src/context-engine/legacy.registration.ts``.
"""
from __future__ import annotations

from .legacy import LegacyContextEngine
from .registry import register_context_engine_for_owner

__all__ = ["register_legacy_context_engine"]


async def _legacy_factory(ctx: dict | None = None) -> LegacyContextEngine:
    return LegacyContextEngine()


def register_legacy_context_engine() -> None:
    """Register the built-in legacy context engine under the core owner.

    Refresh is allowed so tests/bootstrap can re-register after
    module-state resets.
    """
    register_context_engine_for_owner(
        "legacy",
        _legacy_factory,
        "core",
        allow_same_owner_refresh=True,
    )
