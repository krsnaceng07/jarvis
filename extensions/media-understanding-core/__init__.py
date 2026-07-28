"""JARVIS media-understanding-core (shared core package — not a plugin).

Mirrors OpenClaw's ``extensions/media-understanding-core/`` shape:
OpenClaw ships this as a runtime package (no ``openclaw.plugin.json``),
so JARVIS mirrors that with just ``pyproject.toml`` + ``__init__.py``
re-exports. The full runtime + SDK surface lands in Phase 5.16+.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jarvis_sdk.media_understanding_core import (
        UnderstandMediaParams,
        UnderstandMediaRuntimeResult,
        list_runtime_media_understanding_providers,
        understand_media,
    )


def __getattr__(name: str) -> Any:
    """Deferred import — only resolve when callers actually access an export.

    The real ``jarvis_sdk.media_understanding_core`` module is not
    yet ported (Phase 5.16). Until then, accessing any export raises
    ``AttributeError`` with a clear message instead of an
    ``ImportError`` at module import time. This keeps the package
    importable + the workspace members healthy.
    """
    target_module = "jarvis_sdk.media_understanding_core"
    try:
        mod = __import__(target_module, fromlist=[name])
    except ImportError as exc:
        raise AttributeError(
            f"media-understanding-core: '{name}' is not yet available "
            f"(Phase 5.16 port — {target_module} module not ported: {exc})"
        ) from exc
    return getattr(mod, name)


__all__ = [
    "understand_media",
    "list_runtime_media_understanding_providers",
    "UnderstandMediaParams",
    "UnderstandMediaRuntimeResult",
]
