"""Voice Call infra plugin definition and gateway lifecycle hooks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin

from .src.cli import register_voice_call_cli
from .src.config import resolve_voice_call_config
from .src.doctor import run_voice_call_doctor
from .src.plugin_registration import handle_voice_call_rpc, handle_voice_call_tool
from .src.runtime import VoiceCallRuntime

VOICE_CALL_RPC_METHODS: list[str] = [
    "voicecall.initiate",
    "voicecall.start",
    "voicecall.continue",
    "voicecall.continue.start",
    "voicecall.continue.result",
    "voicecall.speak",
    "voicecall.dtmf",
    "voicecall.end",
    "voicecall.status",
    "voicecall.setup",
    "voicecall.smoke",
]


@dataclass(slots=True)
class VoiceCallPlugin(Plugin):
    """Voice Call infra plugin descriptor."""

    id: str = "voice-call"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = (
        "Voice calls for JARVIS: outbound notifications, multi-turn conversations, "
        "full-duplex realtime voice, streaming transcription, and inbound calls with allowlist policies."
    )
    metadata: dict[str, Any] = field(default_factory=dict)
    runtime: VoiceCallRuntime | None = None

    def init(self, ctx: Any = None) -> None:
        """Initialize in-process gateway runtime and attach to context."""
        raw_config = getattr(ctx, "config", {}) if ctx else {}
        cfg_res = resolve_voice_call_config(raw_config)
        cfg = cfg_res.unwrap() if cfg_res.is_ok else None
        self.runtime = VoiceCallRuntime(cfg)
        if ctx and hasattr(ctx, "voice_call_runtime"):
            setattr(ctx, "voice_call_runtime", self.runtime)

    def register_cli(self, subparsers: argparse._SubParsersAction[Any]) -> argparse.ArgumentParser:
        """Register `jarvis voicecall` CLI command."""
        return register_voice_call_cli(subparsers)

    def register_tools(self) -> list[dict[str, Any]]:
        """Declare agent tool definition."""
        return [
            {
                "name": "voice_call",
                "description": "Place outbound phone calls, speak messages, send DTMF tones, and manage live call sessions.",
                "handler": handle_voice_call_tool,
            }
        ]

    def register_rpc_methods(self) -> dict[str, Any]:
        """Declare gateway RPC methods."""
        return {
            method: lambda params, m=method, ctx=None: handle_voice_call_rpc(m, params, ctx)
            for method in VOICE_CALL_RPC_METHODS
        }

    async def doctor(
        self, config: dict[str, Any] | None = None, fix: bool = False
    ) -> dict[str, Any]:
        """Run doctor diagnostic check and auto-fix."""
        res = await run_voice_call_doctor(config=config, fix=fix)
        return res.unwrap() if res.is_ok else {"ok": False, "error": res.unwrap_err()}


voice_call_plugin = VoiceCallPlugin()
entry = voice_call_plugin
