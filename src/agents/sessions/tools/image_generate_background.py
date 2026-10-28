"""
Background task facade for image generation.
"""

import asyncio
import logging
from typing import Optional, Any
from pathlib import Path
from jarvis_media.image_generation.runtime import generate_image
from jarvis_media.image_generation.types import GenerateImageParams

logger = logging.getLogger("jarvis.tools.image_generate_background")

# Simple memory tracking of background generation tasks
_tasks = {}

def get_image_generation_status(task_id: str) -> Optional[dict]:
    return _tasks.get(task_id)


async def execute_image_generation_job(
    task_id: str,
    params: GenerateImageParams,
    # Inject a callback or use an event bus for the completion event
    on_complete: Optional[Any] = None,
):
    """Executes the image generation job and handles completion."""
    _tasks[task_id] = {"status": "running"}
    try:
        result = await generate_image(params)
        
        # Save images to ~/.jarvis/state/media
        # (This is a simplified equivalent of OpenClaw's managed_outgoing_image_records)
        import uuid
        
        saved_paths = []
        attachments = []
        media_dir = Path.home() / ".jarvis" / "state" / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        
        for idx, img in enumerate(result.images):
            # Write to disk
            filename = img.file_name or f"generated_{uuid.uuid4().hex[:8]}.png"
            path = media_dir / filename
            path.write_bytes(img.buffer)
            saved_paths.append(str(path))
            attachments.append({
                "type": "image",
                "path": str(path),
                "mimeType": img.mime_type,
                "name": filename
            })

        summary = f"Generated {len(saved_paths)} image(s) with {result.provider}/{result.model}."
        
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
                    f"[SYSTEM NOTIFICATION: Background image generation '{task_id}' succeeded. "
                    f"Saved {len(saved_paths)} image(s): {saved_paths}. "
                    f"Briefly inform Sir in Nepali in 1 warm sentence that the image is ready.]"
                )
        except Exception as notify_err:
            logger.debug("Voice notification hook note: %s", notify_err)

        if on_complete:
            await on_complete(task_id, _tasks[task_id])

    except Exception as e:
        logger.error(f"Background image generation {task_id} failed: {e}")
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
                    f"[SYSTEM NOTIFICATION: Background image generation '{task_id}' failed: {e}. "
                    f"Briefly inform Sir in Nepali in 1 clear sentence that image generation failed.]"
                )
        except Exception as notify_err:
            logger.debug("Voice notification hook note: %s", notify_err)

        if on_complete:
            await on_complete(task_id, _tasks[task_id])


def schedule_image_generation_background(
    task_id: str,
    params: GenerateImageParams,
    on_complete: Optional[Any] = None,
):
    """Schedules the generation task in the background."""
    asyncio.create_task(execute_image_generation_job(task_id, params, on_complete))
