"""jarvis.shared.runtime_import — runtime dynamic-import helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/runtime-import.ts``.
"""
from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, Optional, Sequence, TypeVar

from .import_specifier import to_safe_import_path

T = TypeVar("T")


def _resolve_runtime_import_specifier(base_url: str, parts: Sequence[str]) -> str:
    joined = "".join(parts)
    safe_joined = to_safe_import_path(joined)
    # Absolute Windows paths and UNC shares become standalone file URLs
    # rather than being resolved against the caller's base URL.
    if safe_joined != joined:
        return safe_joined
    # Python equivalent: use urllib.parse to resolve relative to base.
    from urllib.parse import urljoin
    return urljoin(to_safe_import_path(base_url), joined)


async def import_runtime_module(
    base_url: str,
    parts: Sequence[str],
    import_module: Optional[Callable[[str], Any]] = None,
) -> Any:
    """Import a runtime module through the normalized specifier.

    Mirrors :func:`importRuntimeModule` (``shared/runtime-import.ts``).
    """
    specifier = _resolve_runtime_import_specifier(base_url, parts)
    if import_module is None:
        # Default: use importlib for specifiers; fall back to dynamic import.
        import importlib
        if specifier.startswith("file://"):
            from urllib.parse import urlparse
            from urllib.request import url2pathname
            path = url2pathname(urlparse(specifier).path.lstrip("/"))
            return await _import_path(path)
        return importlib.import_module(specifier)
    res = import_module(specifier)
    if inspect.isawaitable(res):
        return await res
    return res


async def _import_path(path: str) -> Any:
    """Dynamically import a Python file by path."""
    import importlib.util
    import asyncio

    def _load() -> Any:
        spec = importlib.util.spec_from_file_location("_runtime_module", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot import {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return await asyncio.get_event_loop().run_in_executor(None, _load)


__all__ = ["import_runtime_module"]
