"""Test support helpers for provider models, streaming fixtures, and test resets."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable


@dataclass(slots=True)
class StreamingResponseFixture:
    stream: AsyncIterator[bytes]
    get_read_count: Callable[[], int]
    was_canceled: Callable[[], bool]


def create_streaming_response(
    chunk_count: int,
    chunk_size: int = 100,
    text: str | None = None,
    status: int = 200,
) -> StreamingResponseFixture:
    """Create an async streaming response fixture tracking reads and cancellation."""
    reads = 0
    canceled = False

    async def _generator() -> AsyncIterator[bytes]:
        nonlocal reads, canceled
        try:
            for _ in range(chunk_count):
                reads += 1
                if text is not None:
                    yield (text * chunk_size).encode("utf-8")
                else:
                    yield b"x" * chunk_size
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            canceled = True
            raise

    return StreamingResponseFixture(
        stream=_generator(),
        get_read_count=lambda: reads,
        was_canceled=lambda: canceled,
    )


def create_provider_dynamic_model_context(
    provider: str,
    model_id: str,
    models: list[Any],
) -> dict[str, Any]:
    """Create dynamic model resolution context for provider catalog tests."""
    return {
        "provider": provider,
        "modelId": model_id,
        "modelRegistry": {
            "find": lambda p_id, m_id: next(
                (
                    m
                    for m in models
                    if getattr(m, "provider", "").lower() == p_id.lower()
                    and getattr(m, "id", "").lower() == m_id.lower()
                ),
                None,
            )
        },
    }
