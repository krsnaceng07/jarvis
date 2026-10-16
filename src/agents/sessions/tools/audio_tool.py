"""jarvis.agents.sessions.tools.audio_tool — Host audio & volume management tool.

OpenClaw parity:
Gives the agent accurate, verified, hardware-grounded volume and audio control on Windows:
- Query volume percentage and mute status from Windows Core Audio.
- Set volume to exact percentage [0, 100] with physical readback verification.
- Adjust volume up/down by relative delta (e.g. +10%, -15%).
- Mute, unmute, or toggle mute with verification.
"""

from __future__ import annotations

from typing import Any, Optional

from src.system.audio_controller import AudioController
from .tool_definition_wrapper import AgentTool

AUDIO_ACTIONS = (
    "get_volume",
    "set_volume",
    "adjust_volume",
    "mute",
    "unmute",
    "toggle_mute",
)


def create_audio_tool_definition() -> dict[str, Any]:
    return {
        "name": "audio",
        "description": (
            "Control and inspect host PC audio, master volume, and mute status. "
            "Supported actions: "
            "1. 'get_volume': Read current master volume % and mute status from Windows Core Audio. "
            "2. 'set_volume': Set master volume to an exact percentage (0 to 100). "
            "3. 'adjust_volume': Increment or decrement master volume by delta percent (e.g. +10, -15). "
            "4. 'mute': Mute system audio. "
            "5. 'unmute': Unmute system audio. "
            "6. 'toggle_mute': Toggle between muted and unmuted. "
            "All volume changes are physically read back and verified."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(AUDIO_ACTIONS),
                    "description": "Audio action to perform.",
                },
                "percent": {
                    "type": "integer",
                    "description": "Target volume percentage (0 to 100) for set_volume.",
                    "minimum": 0,
                    "maximum": 100,
                },
                "delta": {
                    "type": "integer",
                    "description": "Relative percentage adjustment (e.g. 10 for +10%, -15 for -15%) for adjust_volume.",
                },
            },
            "required": ["action"],
        },
    }


def create_audio_tool(options: Optional[dict[str, Any]] = None) -> AgentTool:
    """Create runtime audio AgentTool backed by AudioController."""
    definition = create_audio_tool_definition()
    controller = AudioController.get_instance()

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: Any = None,
        on_update: Any = None,
    ) -> Any:
        action = str(params.get("action", "")).strip().lower()
        if not action or action not in AUDIO_ACTIONS:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Invalid or missing audio action '{action}'. Supported: {', '.join(AUDIO_ACTIONS)}",
                    }
                ]
            }

        try:
            if action == "get_volume":
                state = controller.get_volume()
                if not state.get("ok"):
                    return {
                        "content": [{"type": "text", "text": state.get("error", "The current volume could not be verified.")}],
                        "data": state,
                    }
                pct = state.get("volume_percent")
                mute_str = "muted" if state.get("muted") else "unmuted"
                text = f"Current Master Volume: {pct}% ({mute_str}). Verified: {state.get('verified')}."
                return {
                    "content": [{"type": "text", "text": text}],
                    "data": state,
                }

            if action == "set_volume":
                pct = params.get("percent")
                if pct is None:
                    return {
                        "content": [
                            {"type": "text", "text": "Error: 'percent' parameter required for set_volume (0-100)."}
                        ]
                    }
                state = controller.set_volume(int(pct))
                if not state.get("ok"):
                    return {
                        "content": [{"type": "text", "text": state.get("error", "Failed to set volume.")}],
                        "data": state,
                    }
                text = (
                    f"Volume set to {state.get('volume_percent')}%. "
                    f"Verified: {state.get('verified')}."
                )
                return {
                    "content": [{"type": "text", "text": text}],
                    "data": state,
                }

            if action == "adjust_volume":
                delta = params.get("delta")
                if delta is None:
                    return {
                        "content": [
                            {"type": "text", "text": "Error: 'delta' parameter required for adjust_volume (e.g. +10, -15)."}
                        ]
                    }
                state = controller.adjust_volume(int(delta))
                if not state.get("ok"):
                    return {
                        "content": [{"type": "text", "text": state.get("error", "Failed to adjust volume.")}],
                        "data": state,
                    }
                sign = "+" if int(delta) >= 0 else ""
                text = (
                    f"Volume adjusted by {sign}{delta}% to {state.get('volume_percent')}%. "
                    f"Verified: {state.get('verified')}."
                )
                return {
                    "content": [{"type": "text", "text": text}],
                    "data": state,
                }

            if action == "mute":
                state = controller.set_mute(True)
                return {
                    "content": [{"type": "text", "text": f"Audio muted. Verified: {state.get('verified')}."}],
                    "data": state,
                }

            if action == "unmute":
                state = controller.set_mute(False)
                return {
                    "content": [{"type": "text", "text": f"Audio unmuted ({state.get('volume_percent')}%). Verified: {state.get('verified')}."}],
                    "data": state,
                }

            if action == "toggle_mute":
                state = controller.toggle_mute()
                mute_str = "Muted" if state.get("muted") else f"Unmuted ({state.get('volume_percent')}%)"
                return {
                    "content": [{"type": "text", "text": f"Audio toggled to {mute_str}. Verified: {state.get('verified')}."}],
                    "data": state,
                }

            return {
                "content": [{"type": "text", "text": f"Unsupported action: {action}"}]
            }

        except Exception as exc:
            return {
                "content": [{"type": "text", "text": f"Audio tool execution failed: {exc}"}]
            }

    return {
        "name": definition["name"],
        "label": "Audio",
        "description": definition["description"],
        "parameters": definition["inputSchema"],
        "execute": _execute,
    }


__all__ = ["create_audio_tool", "create_audio_tool_definition"]
