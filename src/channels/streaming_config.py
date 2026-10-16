"""jarvis.channels.streaming_config — channel streaming & progress draft config resolution.

OpenClaw parity: mirrors ``src/channels/streaming.ts``.

Resolves per-channel streaming configuration:
- mode: "off" | "partial" | "block" | "progress"
- progress:
  - label: str | bool
  - labels: list[str]
  - tool_progress: bool (default True)
  - command_text: "status" | "raw" (default "status")
  - commentary: bool (default False)
  - max_lines: int (default 8)
  - max_line_chars: int (default 120)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

StreamingMode = Literal["off", "partial", "block", "progress"]
CommandTextMode = Literal["status", "raw"]


@dataclass
class ChannelProgressConfig:
    label: str | bool | None = "auto"
    labels: list[str] = field(default_factory=lambda: ["Working"])
    tool_progress: bool = True
    command_text: CommandTextMode = "status"
    commentary: bool = False
    narration: bool = True
    max_lines: int = 8
    max_line_chars: int = 120


@dataclass
class ChannelStreamingConfig:
    mode: StreamingMode = "off"
    progress: ChannelProgressConfig = field(default_factory=ChannelProgressConfig)


DEFAULT_CHANNEL_STREAMING_MODES: dict[str, StreamingMode] = {
    "telegram": "progress",
    "slack": "progress",
    "mattermost": "partial",
    "msteams": "partial",
    "discord": "off",
    "matrix": "off",
}


def resolve_channel_streaming_mode(
    channel: str,
    channel_cfg: dict[str, Any] | None = None,
) -> StreamingMode:
    """Resolve the effective streaming mode for *channel*.

    Default rules:
    - Telegram, Slack: "progress"
    - Mattermost, MS Teams: "partial"
    - Discord, Matrix: "off"
    """
    default_mode = DEFAULT_CHANNEL_STREAMING_MODES.get(channel.lower(), "off")

    if not channel_cfg or not isinstance(channel_cfg, dict):
        return default_mode

    streaming = channel_cfg.get("streaming")
    if isinstance(streaming, dict):
        mode = streaming.get("mode")
        if isinstance(mode, str) and mode.lower() in ("off", "partial", "block", "progress"):
            return mode.lower()  # type: ignore[return-value]

    return default_mode


def resolve_channel_progress_config(
    channel: str,
    channel_cfg: dict[str, Any] | None = None,
) -> ChannelProgressConfig:
    """Resolve the progress config for *channel*."""
    progress_cfg = ChannelProgressConfig()

    if not channel_cfg or not isinstance(channel_cfg, dict):
        return progress_cfg

    streaming = channel_cfg.get("streaming")
    if isinstance(streaming, dict):
        prog = streaming.get("progress")
        if isinstance(prog, dict):
            if "label" in prog:
                lbl = prog["label"]
                if isinstance(lbl, (str, bool)) or lbl is None:
                    progress_cfg.label = lbl
            if "labels" in prog and isinstance(prog["labels"], list):
                progress_cfg.labels = [str(x) for x in prog["labels"] if x]
            if "toolProgress" in prog and isinstance(prog["toolProgress"], bool):
                progress_cfg.tool_progress = prog["toolProgress"]
            if "commandText" in prog and prog["commandText"] in ("status", "raw"):
                progress_cfg.command_text = prog["commandText"]
            if "commentary" in prog and isinstance(prog["commentary"], bool):
                progress_cfg.commentary = prog["commentary"]
            if "narration" in prog and isinstance(prog["narration"], bool):
                progress_cfg.narration = prog["narration"]
            if "maxLines" in prog and isinstance(prog["maxLines"], int):
                progress_cfg.max_lines = max(1, prog["maxLines"])
            if "maxLineChars" in prog and isinstance(prog["maxLineChars"], int):
                progress_cfg.max_line_chars = max(10, prog["maxLineChars"])

    return progress_cfg


def resolve_channel_streaming_config(
    channel: str,
    channel_cfg: dict[str, Any] | None = None,
) -> ChannelStreamingConfig:
    """Resolve full ChannelStreamingConfig object for *channel*."""
    mode = resolve_channel_streaming_mode(channel, channel_cfg)
    prog = resolve_channel_progress_config(channel, channel_cfg)
    return ChannelStreamingConfig(mode=mode, progress=prog)


__all__ = [
    "ChannelProgressConfig",
    "ChannelStreamingConfig",
    "CommandTextMode",
    "StreamingMode",
    "resolve_channel_progress_config",
    "resolve_channel_streaming_config",
    "resolve_channel_streaming_mode",
]
