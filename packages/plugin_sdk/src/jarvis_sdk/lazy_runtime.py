"""jarvis_sdk.lazy_runtime — deferred module loader.

OpenClaw parity: mirrors ``openclaw/plugin-sdk/lazy-runtime``'s
``createLazyRuntimeModule``. Lets a plugin defer heavy imports
(LLM clients, embedding models, LanceDB) until the host actually
needs them — keeps plugin entry import fast and avoids pulling
in optional dependencies until they're actually used.

Architecture
============
The OpenClaw SDK is consumed by the host and by extensions. We
mirror the lazy-import contract: extensions call
``createLazyRuntimeModule(() => import("./heavy.js"))`` and the
host awaits the resulting promise. Failure is sticky: if the
first call raises, the next call retries instead of caching the
broken state — that matches OpenClaw's ``ProviderAdapterEmbeddings``
behavior in ``memory-lancedb/index.ts``.

Parity
======
- ``createLazyRuntimeModule(load_fn)`` returns a function whose
  result is a coroutine that resolves to the loaded module.
- The loader is invoked once per ``load()`` call on success
  (results are memoized; failures invalidate the cache).
- Synchronous-failure imports raise immediately (OpenClaw's
  ``createLazyRuntimeModule`` propagates the import error).

Dependencies
============
- ``importlib`` (stdlib) for the actual module loading.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable  # noqa: TCH003
from typing import Any, TypeVar

_T = TypeVar("_T")


def create_lazy_runtime_module(
    load_fn: Callable[[], Awaitable[_T] | _T],
) -> Callable[[], Awaitable[_T]]:
    """Mirror OpenClaw's ``createLazyRuntimeModule``.

    The returned function awaits the loader's result and caches
    it. Synchronous returns are wrapped in a coroutine; the
    caller always awaits.

    Parameters
    ----------
    load_fn
        A no-argument callable that returns either the module (or
        any object) synchronously, or an awaitable that resolves to
        the same. OpenClaw's signature is ``() => import("./x.js")``;
        ours is ``Callable[[], Awaitable[_T] | _T]``.

    Returns
    -------
    A callable that returns a coroutine. Cached on success;
    failure clears the cache so the next call retries.
    """
    cache: dict[str, Any] = {}

    async def load() -> _T:
        if "value" in cache:
            return cache["value"]  # type: ignore[no-any-return]
        try:
            value = load_fn()
            if hasattr(value, "__await__"):
                value = await value  # type: ignore[assignment]
            cache["value"] = value
            return value  # type: ignore[no-any-return]
        except Exception:
            # Mirror OpenClaw: failed import does not cache; the
            # next load retries the underlying loader.
            cache.pop("value", None)
            raise

    return load


__all__ = ["create_lazy_runtime_module"]
