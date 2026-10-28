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
        task_id = kwargs.get("taskId") or kwargs.get("task_id")
        from .image_generate_background import _tasks

        if not task_id:
            if _tasks:
                task_id = list(_tasks.keys())[-1]
            else:
                return {
                    "status": "none",
                    "message": "No active or recent image generation task found for this session.",
                }
        task_info = get_image_generation_status(task_id)
        if not task_info:
            return {"status": "not_found", "task_id": task_id, "error": f"Task {task_id} not found."}

        st = task_info.get("status", "unknown")
        if st == "failed":
            err = task_info.get("error", "Unknown error")
            return {
                "status": "failed",
                "task_id": task_id,
                "error": err,
                "message": f"Image generation task {task_id} FAILED: {err}. Report this failure honestly to the user.",
            }
        elif st in ("succeeded", "completed"):
            paths = task_info.get("paths", [])
            return {
                "status": "succeeded",
                "task_id": task_id,
                "paths": paths,
                "summary": task_info.get("summary", ""),
                "message": f"Image generation task {task_id} completed successfully. Saved images: {paths}.",
            }
        else:
            return {
                "status": st,
                "task_id": task_id,
                "message": f"Image generation task {task_id} is currently {st} in the background.",
            }
        
    # Default generate action
    prompt = kwargs.get("prompt")
    if not prompt:
        return {"error": "Prompt is required for image generation."}

    cfg = getattr(ctx, "config", {}) if ctx else {}
    providers = list_image_generation_providers(cfg)
    if not providers:
        return {
            "status": "error",
            "error": (
                "No image generation provider or API key is currently configured. "
                "Report this clearly to the user and ask how they would like to proceed "
                "(e.g. configuring an API key, or using a specific service like ChatGPT or Gemini if they wish). "
                "STRICT BAN: NEVER automatically navigate to ChatGPT or any external website unless the user explicitly requested that platform by name."
            ),
        }

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
                "task_id": {"type": "string", "description": "Task ID to check status for (optional; defaults to latest task)"},
                "taskId": {"type": "string", "description": "Task ID alias to check status for"},
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
