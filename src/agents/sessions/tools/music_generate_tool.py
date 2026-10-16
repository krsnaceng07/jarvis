"""
Music Generate Tool definition for JARVIS agent sessions.
"""
from typing import Any, Dict
import uuid

from jarvis_media.music_generation.types import GenerateMusicParams
from jarvis_media.music_generation.provider_registry import list_music_generation_providers
from .music_generate_background import schedule_music_generation_background, get_music_generation_status


def music_generate_tool_handler(ctx: Any, kwargs: dict[str, Any]) -> Any:
    action = kwargs.get("action", "generate")
    
    if action == "list":
        providers = list_music_generation_providers(ctx.config)
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
        return get_music_generation_status(task_id) or {"error": "Task not found."}
        
    prompt = kwargs.get("prompt")
    if not prompt:
        return {"error": "Prompt is required for music generation."}
        
    # Deduplication check
    from .music_generate_background import _tasks
    for tid, tinfo in _tasks.items():
        if tinfo.get("prompt") == prompt and tinfo.get("model") == kwargs.get("model"):
            if tinfo["status"] in ("queued", "running"):
                return {"status": "started", "task_id": tid, "message": "Already running task returned."}
            elif tinfo["status"] == "succeeded":
                # Check if recently completed (simplified)
                return {"status": "succeeded", "task_id": tid, "message": "Recently completed task returned.", "attachments": tinfo.get("attachments", [])}
                
    task_id = f"mus_{uuid.uuid4().hex[:8]}"
    
    cfg = getattr(ctx, "config", {}) if ctx else {}
    agent_id = getattr(ctx, "agent_id", "") if ctx else ""
    params = GenerateMusicParams(
        cfg=cfg,
        prompt=prompt,
        agent_dir=agent_id,
        model_override=kwargs.get("model"),
        duration_seconds=kwargs.get("durationSeconds"),
        instrumental=kwargs.get("instrumental"),
        lyrics=kwargs.get("lyrics"),
        image=kwargs.get("image"),
        images=kwargs.get("images"),
        format=kwargs.get("format"),
        filename=kwargs.get("filename"),
    )
    
    async def on_complete(tid: str, result: Dict[Any, Any]):
        if ctx and hasattr(ctx, "send_custom_message"):
            if result.get("status") == "succeeded":
                # Wake the agent session with the completed attachment
                await ctx.send_custom_message(
                    f"Background music generation {tid} succeeded.",
                    role="system",
                    attachments=result.get("attachments", [])
                )
            else:
                await ctx.send_custom_message(
                    f"Background music generation {tid} failed: {result.get('error')}",
                    role="system"
                )
        
    schedule_music_generation_background(task_id, params, on_complete)
    
    # Register prompt to the tracking
    _tasks[task_id]["prompt"] = prompt
    _tasks[task_id]["model"] = kwargs.get("model")
    
    return {
        "status": "started",
        "task_id": task_id,
        "message": "Music generation started in background. The agent will be notified upon completion.",
        "details": {
            "prompt": prompt,
            "model": kwargs.get("model", "default")
        }
    }


def define_music_generate_tool() -> Dict[str, Any]:
    """Returns the Music Generate tool plugin definition."""
    
    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> Any:
        return music_generate_tool_handler(ctx, params)

    return {
        "name": "music_generate",
        "description": "Create music. Runs asynchronously.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["generate", "status", "list"], "description": "Action to perform"},
                "prompt": {"type": "string", "description": "Music generation prompt"},
                "model": {"type": "string", "description": "Model override"},
                "durationSeconds": {"type": "number", "description": "Duration in seconds"},
                "instrumental": {"type": "boolean", "description": "Instrumental only"},
                "lyrics": {"type": "string", "description": "Custom lyrics"},
                "image": {"type": "string", "description": "Single reference image path or URL"},
                "images": {"type": "array", "items": {"type": "string"}, "description": "Multiple reference images"},
                "format": {"type": "string", "enum": ["mp3", "wav"], "description": "Output format hint"},
                "filename": {"type": "string", "description": "Output filename hint"}
            },
        },
        "execute": _execute,
    }
