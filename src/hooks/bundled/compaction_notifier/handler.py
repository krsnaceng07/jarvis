"""Bundled compaction-notifier hook — mirrors OpenClaw ``bundled/compaction-notifier``.

Fires on ``session:compact:before`` and ``session:compact:after`` to append
a brief human-readable notification to ``event.messages``.  The host reads
those messages and surfaces them to the operator (e.g. via the HUD log or
Telegram).
"""

from __future__ import annotations

import logging

_log = logging.getLogger("jarvis.hooks.bundled.compaction_notifier")

_BEFORE_MSG = "🗜️ Context compaction starting — condensing conversation history…"
_AFTER_MSG = "✅ Context compaction complete — conversation history condensed."


def handle(event) -> None:  # type: ignore[no-untyped-def]
    """Append a compaction notification to the event's messages list."""
    try:
        key = f"{event.type}:{event.action}"
        if key == "session:compact:before":
            event.messages.append(_BEFORE_MSG)
        elif key == "session:compact:after":
            event.messages.append(_AFTER_MSG)
        else:
            _log.debug("compaction-notifier: unrecognised event key %r", key)
    except Exception as e:  # noqa: BLE001
        _log.debug("compaction-notifier hook failed: %s", e)
