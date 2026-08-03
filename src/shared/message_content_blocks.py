"""jarvis.shared.message_content_blocks — object content-block visitor.

OpenClaw parity: mirrors ``openclaw-main/src/shared/message-content-blocks.ts``.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


def visit_object_content_blocks(
    message: Any,
    visitor: Callable[[Dict[str, Any]], None],
) -> None:
    """Visit every object-shaped content block in a message payload.

    Mirrors :func:`visitObjectContentBlocks`
    (``shared/message-content-blocks.ts``).
    """
    if not message or not isinstance(message, dict):
        return
    content = message.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, dict):
            visitor(block)


__all__ = ["visit_object_content_blocks"]
