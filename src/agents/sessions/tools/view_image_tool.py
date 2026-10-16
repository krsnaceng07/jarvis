"""
View Image Tool
"""

from typing import Any, Dict
import logging

logger = logging.getLogger("jarvis.tools.view_image")

async def view_image_tool_handler(ctx: Any, kwargs: dict[str, Any]) -> Any:
    # 1. Gather parameters
    path = kwargs.get("path")
    paths = kwargs.get("paths", [])
    
    if path:
        paths.append(path)
        
    # Deduplicate while preserving order
    unique_paths = []
    for p in paths:
        if p not in unique_paths:
            unique_paths.append(p)
            
    if not unique_paths:
        raise ValueError("path required: provide a path or URL to an image")

    prompt = kwargs.get("prompt", "Describe this image.")
    
    cfg = getattr(ctx, "config", {}) if ctx else {}
    max_images = kwargs.get("maxImages", 20)
    
    if len(unique_paths) > max_images:
        unique_paths = unique_paths[:max_images]
        logger.warning(f"view_image: truncated to {max_images} images")

    # In a real openclaw implementation, we use model_registry or a resolver here.
    # This just mocks the interface requirement for now.
    try:
        content = []
        for p in unique_paths:
            content.append({"type": "image_url", "image_url": {"url": p}})
        content.append({"type": "text", "text": prompt})
        
        return {
            "content": content,
            "details": {"processed": len(unique_paths)}
        }
    except Exception as e:
        return {
            "details": {"error": str(e)}
        }

def define_view_image_tool() -> Dict[str, Any]:
    """Returns the view_image tool plugin definition."""
    
    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> Any:
        return await view_image_tool_handler(ctx, params)

    return {
        "name": "view_image",
        "description": "Semantic image inspection capability. Allows analyzing local or remote images.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "One local image path or permitted URL."},
                "paths": {"type": "array", "items": {"type": "string"}, "description": "Multiple local image paths or permitted URLs."},
                "maxImages": {"type": "integer", "description": "Limits the combined list, defaults to 20.", "default": 20},
                "prompt": {"type": "string", "description": "Prompt for semantic inspection.", "default": "Describe this image."}
            },
        },
        "execute": _execute
    }
