"""jarvis.channels — OpenClaw ``src/channels/`` parity module.

Wave 16 additions:
  - typing: TypingIndicator
  - thread: ThreadContext, resolve_thread_id, thread_reply_target
  - targets: ChannelTarget, resolve_send_target
  - model_overrides: resolve_channel_model
  - session_envelope: SessionEnvelope
"""

from .typing import TypingIndicator
from .thread import ThreadContext, resolve_thread_id, thread_reply_target
from .targets import ChannelTarget, resolve_send_target
from .model_overrides import resolve_channel_model
from .session_envelope import SessionEnvelope

__all__ = [
    "ChannelTarget",
    "SessionEnvelope",
    "ThreadContext",
    "TypingIndicator",
    "resolve_channel_model",
    "resolve_send_target",
    "resolve_thread_id",
    "thread_reply_target",
]
