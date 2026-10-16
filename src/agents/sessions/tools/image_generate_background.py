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
        
        # In a full JARVIS implementation, this is where we'd wake the agent 
        # or push the attachment via channels_core.
        if on_complete:
            # We assume on_complete is an async callback taking the task_id and result
            await on_complete(task_id, _tasks[task_id])

    except Exception as e:
        logger.error(f"Background image generation {task_id} failed: {e}")
        _tasks[task_id] = {
            "status": "failed",
            "error": str(e)
        }
        if on_complete:
            await on_complete(task_id, _tasks[task_id])


def schedule_image_generation_background(
    task_id: str,
    params: GenerateImageParams,
    on_complete: Optional[Any] = None,
):
    """Schedules the generation task in the background."""
    asyncio.create_task(execute_image_generation_job(task_id, params, on_complete))
