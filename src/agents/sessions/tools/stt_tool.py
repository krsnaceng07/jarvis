"""
STT Tool definition for JARVIS agent sessions.
"""
from typing import Any, Dict

from jarvis_media.stt.types import GenerateSttParams
from jarvis_media.stt.provider_registry import list_stt_providers
from jarvis_media.stt.runtime import transcribe_audio


async def stt_tool_handler(ctx: Any, kwargs: dict[str, Any]) -> Any:
    action = kwargs.get("action", "transcribe")
    
    if action == "list":
        providers = list_stt_providers(ctx.config)
        return {
            "status": "success",
            "providers": [
                {
                    "id": p.id,
                    "default_model": p.default_model,
                    "models": p.models,
                }
                for p in providers
            ]
        }
    
    audio_base64 = kwargs.get("audioBase64")
    audio_url = kwargs.get("audioUrl")
    if not audio_base64 and not audio_url:
        return {"error": "audioBase64 or audioUrl is required for STT."}
        
    cfg = getattr(ctx, "config", {}) if ctx else {}
    agent_id = getattr(ctx, "agent_id", "") if ctx else ""
    params = GenerateSttParams(
        cfg=cfg,
        audio_base64=audio_base64,
        audio_url=audio_url,
        audio_mime_type=kwargs.get("audioMimeType", "audio/wav"),
        agent_dir=agent_id,
        model_override=kwargs.get("model"),
        language=kwargs.get("language"),
        timeout_ms=kwargs.get("timeoutMs"),
    )
    
    try:
        result = await transcribe_audio(params)
        
        return {
            "status": "success",
            "provider": result.provider,
            "model": result.model,
            "language": result.language,
            "text": result.text,
        }
    except Exception as e:
        return {"error": str(e)}


def define_stt_tool() -> Dict[str, Any]:
    """Returns the STT tool plugin definition."""
    
    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> Any:
        return await stt_tool_handler(ctx, params)

    return {
        "name": "stt",
        "description": "Speech-to-text transcription. Runs synchronously.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action to perform (transcribe, list)"},
                "audioBase64": {"type": "string", "description": "Base64 encoded audio"},
                "audioUrl": {"type": "string", "description": "URL of the audio to transcribe"},
                "audioMimeType": {"type": "string", "description": "audio/wav, audio/mp3, etc."},
                "model": {"type": "string", "description": "Model override"},
                "language": {"type": "string", "description": "Language code"},
                "timeoutMs": {"type": "number", "description": "Timeout in ms"},
            },
        },
        "execute": _execute,
    }
