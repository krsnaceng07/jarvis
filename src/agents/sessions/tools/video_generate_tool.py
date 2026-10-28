"""
Video Generate Tool definition for JARVIS agent sessions.
"""
from typing import Any, Dict
import uuid

from jarvis_media.video_generation.types import GenerateVideoParams
from jarvis_media.video_generation.provider_registry import list_video_generation_providers
from .video_generate_background import schedule_video_generation_background, get_video_generation_status


def video_generate_tool_handler(ctx: Any, kwargs: dict[str, Any]) -> Any:
    action = kwargs.get("action", "generate")
    
    cfg = getattr(ctx, "config", None) if ctx else None
    if not cfg:
        try:
            from src.config.config import load_config

            cfg = load_config()
        except Exception:
            cfg = {}

    if action == "list":
        # Return list of configured providers
        providers = list_video_generation_providers(cfg)
        return {
            "status": "success",
            "providers": [
                {
                    "id": p.id,
                    "default_model": p.default_model,
                    "models": p.models,
                }
                for p in providers
            ],
        }

    if action == "status":
        task_id = kwargs.get("taskId") or kwargs.get("task_id")
        from .video_generate_background import _tasks

        if not task_id:
            if _tasks:
                task_id = list(_tasks.keys())[-1]
            else:
                return {
                    "status": "none",
                    "message": "No active or recent video generation task found for this session.",
                }
        task_info = get_video_generation_status(task_id)
        if not task_info:
            return {"status": "not_found", "task_id": task_id, "error": f"Task {task_id} not found."}

        st = task_info.get("status", "unknown")
        if st == "failed":
            err = task_info.get("error", "Unknown error")
            return {
                "status": "failed",
                "task_id": task_id,
                "error": err,
                "message": f"Video generation task {task_id} FAILED: {err}. Report this failure honestly to the user.",
            }
        elif st in ("succeeded", "completed"):
            paths = task_info.get("paths", [])
            return {
                "status": "succeeded",
                "task_id": task_id,
                "paths": paths,
                "summary": task_info.get("summary", ""),
                "message": f"Video generation task {task_id} completed successfully. Saved videos: {paths}.",
            }
        else:
            return {
                "status": st,
                "task_id": task_id,
                "message": f"Video generation task {task_id} is currently {st} in the background.",
            }

    # Default generate action
    prompt = kwargs.get("prompt")
    if not prompt:
        return {"error": "Prompt is required for video generation."}

    providers = list_video_generation_providers(cfg)
    if not providers:
        return {
            "status": "error",
            "error": (
                "No video generation provider or model is currently configured on this system. "
                "Report this clearly to the user and check available providers with action='list'."
            ),
            "message": "Cannot start video generation: No video generation model configured on this host.",
        }

    task_id = f"vid_{uuid.uuid4().hex[:8]}"
    
    cfg = getattr(ctx, "config", {}) if ctx else {}
    agent_id = getattr(ctx, "agent_id", "") if ctx else ""
    params = GenerateVideoParams(
        cfg=cfg,
        prompt=prompt,
        agent_dir=agent_id,
        model_override=kwargs.get("model"),
        aspect_ratio=kwargs.get("aspectRatio"),
        resolution=kwargs.get("resolution"),
        duration_seconds=kwargs.get("durationSeconds"),
        fps=kwargs.get("fps"),
        timeout_ms=kwargs.get("timeoutMs"),
    )
    
    async def on_complete(tid: str, result: Dict[Any, Any]):
        pass
        
    schedule_video_generation_background(task_id, params, on_complete)
    
    return {
        "status": "started",
        "task_id": task_id,
        "message": "Video generation started in background. The agent will be notified upon completion.",
        "details": {
            "prompt": prompt,
            "model": kwargs.get("model", "default")
        }
    }


def define_video_generate_tool() -> Dict[str, Any]:
    """Returns the Video Generate tool plugin definition."""
    
    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> Any:
        return video_generate_tool_handler(ctx, params)

    return {
        "name": "video_generate",
        "description": "Create or edit videos. Runs asynchronously.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action to perform (generate, list, status)"},
                "task_id": {"type": "string", "description": "Task ID to check status for (optional; defaults to latest task)"},
                "taskId": {"type": "string", "description": "Task ID alias to check status for"},
                "prompt": {"type": "string", "description": "Video generation prompt"},
                "model": {"type": "string", "description": "Model override"},
                "aspectRatio": {"type": "string", "description": "Aspect ratio like 16:9"},
                "resolution": {"type": "string", "description": "Resolution like 1080p"},
                "durationSeconds": {"type": "number", "description": "Duration in seconds"},
                "fps": {"type": "number", "description": "Frames per second"},
                "timeoutMs": {"type": "number", "description": "Timeout in ms"},
            },
        },
        "execute": _execute,
    }
