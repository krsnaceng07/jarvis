"""
TTS Tool definition for JARVIS agent sessions.
"""
from typing import Any, Dict
import uuid
from pathlib import Path

from jarvis_media.tts.types import GenerateTtsParams
from jarvis_media.tts.provider_registry import list_tts_providers
from jarvis_media.tts.runtime import generate_tts


async def tts_tool_handler(ctx: Any, kwargs: dict[str, Any]) -> Any:
    action = kwargs.get("action", "generate")
    
    if action == "list":
        providers = list_tts_providers(ctx.config)
        return {
            "status": "success",
            "providers": [
                {
                    "id": p.id,
                    "default_model": p.default_model,
                    "models": p.models,
                    "voices": p.voices,
                }
                for p in providers
            ]
        }
    
    text = kwargs.get("text")
    if not text:
        return {"error": "Text is required for TTS."}
        
    cfg = getattr(ctx, "config", {}) if ctx else {}
    agent_id = getattr(ctx, "agent_id", "") if ctx else ""
    params = GenerateTtsParams(
        cfg=cfg,
        text=text,
        agent_dir=agent_id,
        model_override=kwargs.get("model"),
        voice_override=kwargs.get("voice"),
        speed=kwargs.get("speed"),
        pitch=kwargs.get("pitch"),
        output_format=kwargs.get("outputFormat"),
        timeout_ms=kwargs.get("timeoutMs"),
    )
    
    try:
        result = await generate_tts(params)
        
        media_dir = Path.home() / ".jarvis" / "state" / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        
        audio_asset = result.audio
        filename = audio_asset.file_name or f"tts_{uuid.uuid4().hex[:8]}.mp3"
        path = media_dir / filename
        path.write_bytes(audio_asset.buffer)
        
        return {
            "status": "success",
            "provider": result.provider,
            "model": result.model,
            "voice": result.voice,
            "path": str(path),
            "attachment": {
                "type": "audio",
                "path": str(path),
                "mimeType": audio_asset.mime_type,
                "name": filename
            }
        }
    except Exception as e:
        return {"error": str(e)}


def define_tts_tool() -> Dict[str, Any]:
    """Returns the TTS tool plugin definition."""
    
    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> Any:
        return await tts_tool_handler(ctx, params)

    return {
        "name": "tts",
        "description": "Text-to-speech generation. Runs synchronously.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action to perform (generate, list)"},
                "text": {"type": "string", "description": "Text to convert to speech"},
                "model": {"type": "string", "description": "Model override"},
                "voice": {"type": "string", "description": "Voice identifier"},
                "speed": {"type": "number", "description": "Playback speed"},
                "pitch": {"type": "number", "description": "Pitch adjustment"},
                "outputFormat": {"type": "string", "description": "mp3, wav, etc."},
                "timeoutMs": {"type": "number", "description": "Timeout in ms"},
            },
        },
        "execute": _execute,
    }
