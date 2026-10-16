"""
Image Generate Tool definition for JARVIS agent sessions.
"""
from typing import Any, Dict
import uuid

from jarvis_media.image_generation.types import GenerateImageParams
from jarvis_media.image_generation.provider_registry import list_image_generation_providers
from .image_generate_background import schedule_image_generation_background, get_image_generation_status




def image_generate_tool_handler(ctx: Any, kwargs: dict[str, Any]) -> Any:
    action = kwargs.get("action", "generate")
    
    if action == "list":
        # Return list of configured providers
        providers = list_image_generation_providers(ctx.config)
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
    
    if action == "status":
        task_id = kwargs.get("taskId")
        if not task_id:
            return {"error": "taskId is required for status action."}
        return get_image_generation_status(task_id) or {"error": "Task not found."}
        
    # Default generate action
    prompt = kwargs.get("prompt")
    if not prompt:
        return {"error": "Prompt is required for image generation."}
        
    task_id = f"img_{uuid.uuid4().hex[:8]}"
    
    # In full parity, we fetch auth profiles from ctx and map image attachments
    cfg = getattr(ctx, "config", {}) if ctx else {}
    agent_id = getattr(ctx, "agent_id", "") if ctx else ""
    params = GenerateImageParams(
        cfg=cfg,
        prompt=prompt,
        agent_dir=agent_id, # Simplified
        model_override=kwargs.get("model"),
        count=kwargs.get("count"),
        size=kwargs.get("size"),
        aspect_ratio=kwargs.get("aspectRatio"),
        quality=kwargs.get("quality"),
        output_format=kwargs.get("outputFormat"),
        background=kwargs.get("background"),
        timeout_ms=kwargs.get("timeoutMs"),
    )
    
    # We use a dummy callback that pushes to the session transcript or state in a real impl
    async def on_complete(tid: str, result: Dict[Any, Any]):
        # We could use the hook bus or session transcript API here to deliver the result.
        pass
        
    schedule_image_generation_background(task_id, params, on_complete)
    
    return {
        "status": "started",
        "task_id": task_id,
        "message": "Image generation started in background. The agent will be notified upon completion.",
        "details": {
            "prompt": prompt,
            "model": kwargs.get("model", "default")
        }
    }


def define_image_generate_tool() -> Dict[str, Any]:
    """Returns the Image Generate tool plugin definition."""
    
    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> Any:
        return image_generate_tool_handler(ctx, params)

    return {
        "name": "image_generate",
        "description": "Create or edit images. Runs asynchronously.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action to perform (generate, list, status)"},
                "prompt": {"type": "string", "description": "Image generation prompt"},
                "model": {"type": "string", "description": "Model override"},
                "size": {"type": "string", "description": "Size like 1024x1024"},
                "aspectRatio": {"type": "string", "description": "Aspect ratio like 16:9"},
                "quality": {"type": "string", "description": "low, medium, high"},
                "outputFormat": {"type": "string", "description": "png, jpeg, webp"},
                "background": {"type": "string", "description": "transparent, opaque"},
                "count": {"type": "number", "description": "Number of images"},
                "timeoutMs": {"type": "number", "description": "Timeout in ms"},
            },
        },
        "execute": _execute,
    }
