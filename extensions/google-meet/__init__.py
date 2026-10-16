"""Google Meet extension for JARVIS.

Full feature parity with OpenClaw's google-meet extension.
Provides Google Meet automation, REST API integration, Chrome browser proxy,
audio routing (Sox / PipeWire), OAuth flows, transcripts, attendance, and export bundles.
"""

from .plugin import entry, get_google_meet_runtime
from .src.config import GoogleMeetConfig, resolve_google_meet_config
from .src.meet_url import (
    parse_google_meet_target,
    normalize_google_meet_url,
    is_valid_google_meet_url,
)
from .src.runtime import GoogleMeetRuntime

__all__ = [
    "entry",
    "get_google_meet_runtime",
    "GoogleMeetConfig",
    "resolve_google_meet_config",
    "parse_google_meet_target",
    "normalize_google_meet_url",
    "is_valid_google_meet_url",
    "GoogleMeetRuntime",
]
