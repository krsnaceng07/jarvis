"""jarvis.logging.node_require — Node.js-compatible createRequire wrapper.

OpenClaw parity: mirrors
``openclaw-main/src/logging/node-require.ts``.

Public surface:

- :func:`resolve_node_require_from_meta`
"""
from __future__ import annotations

import importlib
from typing import Any, Callable, Optional


def resolve_node_require_from_meta(meta_url: str) -> Optional[Callable[..., Any]]:
    """Resolve a Node-style ``createRequire`` from Python imports.

    Mirrors :func:`resolveNodeRequireFromMeta` (``logging/node-require.ts``).
    """
    if not isinstance(meta_url, str) or not meta_url:
        return None
    # The Python equivalent of createRequire is ``importlib.import_module`` plus
    # ``importlib.util.spec_from_file_location``. We expose a factory that
    # callers can use to load a module from a file path.
    try:
        import importlib.util as importlib_util
        import sys as _sys

        def _load(path: str) -> Any:
            if not isinstance(path, str) or not path:
                raise ImportError(f"Cannot load {path!r}")
            spec = importlib_util.spec_from_file_location(meta_url, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load {path!r}")
            module = importlib_util.module_from_spec(spec)
            _sys.modules[meta_url] = module
            spec.loader.exec_module(module)
            return module

        return _load
    except Exception:
        return None


__all__ = ["resolve_node_require_from_meta"]
