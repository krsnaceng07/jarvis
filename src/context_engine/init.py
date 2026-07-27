"""Context-engine initialization registers built-in engines before plugin resolution.

OpenClaw parity: ``src/context-engine/init.ts``.
"""
from __future__ import annotations

from .legacy_registration import register_legacy_context_engine

__all__ = ["ensure_context_engines_initialized"]

_initialized = False


def ensure_context_engines_initialized() -> None:
    """Ensure all built-in context engines are registered exactly once.

    The legacy engine is always registered as a safe fallback so that
    ``resolve_context_engine()`` can resolve the default "legacy" slot
    without callers needing to remember manual registration. Additional
    engines are registered by their own plugins via
    ``api.register_context_engine()`` during plugin load.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    # Always available - safe fallback for the "legacy" slot default.
    register_legacy_context_engine()
