"""Talk Voice plugin entrypoint.

Registers the /voice and /talkvoice slash command handlers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin
from .voice_command import handle_voice_command


@dataclass(frozen=True, slots=True)
class TalkVoicePlugin(Plugin):
    """Talk Voice command plugin."""

    id: str = "talk-voice"
    kind: str = "tools"
    version: str = "0.1.0"
    description: str = "Manage Talk voice selection (list/set)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Register the voice command."""
        if hasattr(ctx, "register_command"):
            ctx.register_command(
                name="voice",
                native_names={"discord": "talkvoice"},
                description="List/set Talk provider voices (affects iOS Talk playback).",
                accepts_args=True,
                expose_sender_is_owner=True,
                handler=lambda cmd_ctx: handle_voice_command(
                    cmd_ctx, getattr(ctx, "runtime", None)
                ),
            )


talk_voice_plugin = TalkVoicePlugin()
entry = talk_voice_plugin
