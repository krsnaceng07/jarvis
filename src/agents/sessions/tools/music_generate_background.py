"""
Background task facade for music generation.
"""

import asyncio
import logging
from typing import Optional, Any
from pathlib import Path
from jarvis_media.music_generation.runtime import generate_music
from jarvis_media.music_generation.types import GenerateMusicParams

logger = logging.getLogger("jarvis.tools.music_generate_background")

# Simple memory tracking of background generation tasks.
# In a full openclaw port, this uses the real tasks ledger.
_tasks = {}

def get_music_generation_status(task_id: str) -> Optional[dict]:
    return _tasks.get(task_id)


def _cleanup_old_tasks():
    # Keep tasks for deduplication
    pass

async def execute_music_generation_job(
    task_id: str,
    params: GenerateMusicParams,
    on_complete: Optional[Any] = None,
):
    """Executes the music generation job and handles completion."""
    _tasks[task_id] = {"status": "running"}
    try:
        result = await generate_music(params)
        
        import uuid
        
        saved_paths = []
        attachments = []
        media_dir = Path.home() / ".jarvis" / "state" / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        
        for idx, track in enumerate(result.tracks):
            filename = track.file_name or f"generated_{uuid.uuid4().hex[:8]}.mp3"
            path = media_dir / filename
            path.write_bytes(track.buffer)
            saved_paths.append(str(path))
            attachments.append({
                "type": "audio",
                "path": str(path),
                "mimeType": track.mime_type,
                "name": filename
            })

        summary = f"Generated {len(saved_paths)} track(s) with {result.provider}/{result.model}."
        
        _tasks[task_id] = {
            "status": "succeeded",
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
                    f"[SYSTEM NOTIFICATION: Background music generation '{task_id}' succeeded. "
                    f"Saved {len(saved_paths)} audio track(s): {saved_paths}. "
                    f"Briefly inform Sir in Nepali in 1 warm sentence that the music generation is complete and ready.]"
                )
        except Exception as notify_err:
            logger.debug("Voice notification hook note: %s", notify_err)

        if on_complete:
            await on_complete(task_id, _tasks[task_id])

    except Exception as e:
        logger.error(f"Background music generation {task_id} failed: {e}")
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
                    f"[SYSTEM NOTIFICATION: Background music generation '{task_id}' failed: {e}. "
                    f"Briefly inform Sir in Nepali in 1 clear sentence that the music generation failed and why.]"
                )
        except Exception as notify_err:
            logger.debug("Voice notification hook note: %s", notify_err)

        if on_complete:
            await on_complete(task_id, _tasks[task_id])


def schedule_music_generation_background(
    task_id: str,
    params: GenerateMusicParams,
    on_complete: Optional[Any] = None,
):
    """Schedules the generation task in the background."""
    _tasks[task_id] = {"status": "queued"}
    asyncio.create_task(execute_music_generation_job(task_id, params, on_complete))
