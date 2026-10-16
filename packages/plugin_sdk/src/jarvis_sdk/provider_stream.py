"""Shared provider stream-wrapper composition.

Mirrors OpenClaw's ``composeProviderStreamWrappers``
(``src/plugin-sdk/provider-stream-shared.ts``): wrapper factories
compose left to right around a base stream function and falsey
entries are skipped. Family-level seam — providers share this
instead of copying the fold per provider.
"""

from __future__ import annotations

from typing import Callable, TypeVar

F = TypeVar("F")

#: A decorator factory for a stream function, or a falsey skip marker.
StreamWrapperFactory = Callable[[F | None], F | None] | None | bool


def compose_provider_stream_wrappers(
    base: F | None,
    *wrappers: StreamWrapperFactory[F],
) -> F | None:
    """Compose ``wrappers`` left to right around ``base``.

    Falsey wrapper entries (``None``/``False``) are skipped so
    providers can pass conditional wrappers inline.
    """
    stream_fn = base
    for wrapper in wrappers:
        if not wrapper:
            continue
        assert callable(wrapper)
        stream_fn = wrapper(stream_fn)
    return stream_fn


__all__ = ["StreamWrapperFactory", "compose_provider_stream_wrappers"]
