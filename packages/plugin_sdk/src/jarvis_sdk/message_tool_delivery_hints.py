"""jarvis_sdk.message_tool_delivery_hints — delivery hint strings.

OpenClaw parity: mirrors
``openclaw/plugin-sdk/message-tool-delivery-hints``'s
``MESSAGE_TOOL_DELIVERY_HINTS``.

Used by ``memory-lancedb``'s envelope-scrubbing layer to
strip "delivery hint" sentinels that the host injects
before persisting user messages (e.g. ``[delivered]``,
``[silent]``).

Architecture
============
The host inserts these hints at the head of outbound message
bodies to tell downstream tools (memory capture, recall
filter, etc.) how a message was delivered. They're not user
content; they should never be stored as a long-term memory
nor echoed back through a recall hit.

Parity
======
- ``MESSAGE_TOOL_DELIVERY_HINTS`` is a ``frozenset[str]`` of
  exact-match hint strings the host injects. The
  envelope-scrubber consumes this set as part of its
  line-anchored metadata-strip pass.
"""

from __future__ import annotations

# Hint strings the JARVIS host injects at the head of message
# bodies. The memory extension's envelope-scrubber treats any
# line that exactly matches one of these as transport metadata
# and strips it before persisting the body.
MESSAGE_TOOL_DELIVERY_HINTS: frozenset[str] = frozenset(
    {
        "[delivered]",
        "[silent]",
        "[no-reply]",
        "[dm-only]",
        "[group-only]",
        "[owner-only]",
    }
)


__all__ = ["MESSAGE_TOOL_DELIVERY_HINTS"]
