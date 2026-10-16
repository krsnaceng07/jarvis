"""YouTube runtime singleton."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class YouTubeRuntime:
    started: bool = False
    last_action_at_ms: int = 0
    active_video: str = ""
    is_playing: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


_RUNTIME_LOCK = threading.Lock()
_RUNTIME: YouTubeRuntime | None = None


def set_youtube_runtime(runtime: YouTubeRuntime) -> None:
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = runtime


def get_youtube_runtime() -> YouTubeRuntime | None:
    with _RUNTIME_LOCK:
        return _RUNTIME


def reset_youtube_runtime() -> None:
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = None
