"""
Background task facade for video generation.
"""

import asyncio
import logging
from typing import Optional, Any
from pathlib import Path
from jarvis_media.video_generation.runtime import generate_video
from jarvis_media.video_generation.types import GenerateVideoParams

logger = logging.getLogger("jarvis.tools.video_generate_background")

# Simple memory tracking of background generation tasks
_tasks = {}

def get_video_generation_status(task_id: str) -> Optional[dict]:
    return _tasks.get(task_id)


async def execute_video_generation_job(
    task_id: str,
    params: GenerateVideoParams,
    on_complete: Optional[Any] = None,
):
    """Executes the video generation job and handles completion."""
    _tasks[task_id] = {"status": "running"}
    try:
        result = await generate_video(params)
        
        import uuid
        
        saved_paths = []
        attachments = []
        media_dir = Path.home() / ".jarvis" / "state" / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        
        for idx, vid in enumerate(result.videos):
            filename = vid.file_name or f"generated_{uuid.uuid4().hex[:8]}.mp4"
            path = media_dir / filename
            path.write_bytes(vid.buffer)
            saved_paths.append(str(path))
            attachments.append({
                "type": "video",
                "path": str(path),
                "mimeType": vid.mime_type,
                "name": filename
            })

        summary = f"Generated {len(saved_paths)} video(s) with {result.provider}/{result.model}."
        
        _tasks[task_id] = {
            "status": "completed",
            "provider": result.provider,
            "model": result.model,
            "paths": saved_paths,
            "attachments": attachments,
            "summary": summary
        }
        
        # OpenClaw parity: Deliver immediate spoken voice notification to active voice engine
        try:
            from jarvis_voice_pipeline.terminal_app import NativeGeminiLiveEngine
            active = NativeGeminiLiveEngine.get_active_engine()
            if active and hasattr(active, "post_system_notification"):
                active.post_system_notification(
                    f"[SYSTEM NOTIFICATION: Background video generation '{task_id}' succeeded. "
                    f"Saved {len(saved_paths)} video(s): {saved_paths}. "
                    f"Briefly inform Sir in Nepali in 1 warm sentence that the video is ready.]"
                )
        except Exception as notify_err:
            logger.debug("Voice notification hook note: %s", notify_err)

        if on_complete:
            await on_complete(task_id, _tasks[task_id])

    except Exception as e:
        logger.error(f"Background video generation {task_id} failed: {e}")
        _tasks[task_id] = {
            "status": "failed",
            "error": str(e)
        }

        # OpenClaw parity: Deliver immediate failure notification to active voice engine
        try:
            from jarvis_voice_pipeline.terminal_app import NativeGeminiLiveEngine
            active = NativeGeminiLiveEngine.get_active_engine()
            if active and hasattr(active, "post_system_notification"):
                active.post_system_notification(
                    f"[SYSTEM NOTIFICATION: Background video generation '{task_id}' failed: {e}. "
                    f"Briefly inform Sir in Nepali in 1 clear sentence that video generation failed.]"
                )
        except Exception as notify_err:
            logger.debug("Voice notification hook note: %s", notify_err)

        if on_complete:
            await on_complete(task_id, _tasks[task_id])


def schedule_video_generation_background(
    task_id: str,
    params: GenerateVideoParams,
    on_complete: Optional[Any] = None,
):
    """Schedules the generation task in the background."""
    asyncio.create_task(execute_video_generation_job(task_id, params, on_complete))
