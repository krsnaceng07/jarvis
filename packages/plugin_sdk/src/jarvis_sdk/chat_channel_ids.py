"""jarvis_sdk.chat_channel_ids — bundled channel envelope prefixes.

OpenClaw parity: mirrors
``openclaw/plugin-sdk/chat-channel-ids``'s
``BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES``.

Used by ``memory-lancedb``'s envelope-scrubbing layer to
distinguish "real channel envelope" from "user prose that
happens to look like a channel header".

Architecture
============
The bundled channel list is a constant tuple of lowercase
strings that the OpenClaw host injects into inbound
envelopes. The memory plugin uses it to gate the
"marker-free" envelope detector: a ``[<word> ...]`` prefix
is only treated as transport metadata if ``<word>`` is in
this list (or if the prefix carries a timestamp/elapsed
marker that the same detector recognises).

The list is the same across JARVIS: it's an OpenClaw contract
that any new bundled channel must register here.

Parity
======
- ``BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES`` is a
  ``frozenset[str]`` of lowercase bundled-channel names.
  JARVIS ships the same set as OpenClaw; the OpenClaw
  registry is wider (Slack, Discord, Telegram, etc.), so
  we mirror the minimum set that the memory-lancedb
  envelope-scrubber needs today.
"""

from __future__ import annotations

# Bundled channel names that the JARVIS host (and OpenClaw)
# injects as ``[Channel ...]`` envelope prefixes. New channels
# should be registered here.
BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES: frozenset[str] = frozenset(
    {
        "telegram",
        "discord",
        "slack",
        "whatsapp",
        "signal",
        "imessage",
        "line",
        "matrix",
        "mattermost",
        "irc",
        "msteams",
        "googlechat",
        "sms",
        "feishu",
        "lark",
    }
)


__all__ = ["BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES"]
