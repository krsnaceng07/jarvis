"""
Model reference parser for image generation.
"""

from typing import Optional


def parse_image_generation_model_ref(
    model_ref: Optional[str],
) -> Optional[dict[str, str]]:
    """Parse a provider/model string like 'openai/dall-e-3'."""
    if not model_ref:
        return None
    model_ref = model_ref.strip()
    if not model_ref:
        return None

    parts = model_ref.split("/", 1)
    if len(parts) == 2:
        provider = parts[0].strip()
        model = parts[1].strip()
        if provider and model:
            return {"provider": provider, "model": model}
    return None
