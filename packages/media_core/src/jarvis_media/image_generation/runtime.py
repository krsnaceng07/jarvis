"""
Runtime entrypoint for image generation with provider fallback.
"""

from typing import Optional
import logging

from .types import (
    GenerateImageParams,
    GenerateImageRuntimeResult,
    FallbackAttempt,
    ImageGenerationRequest,
    ImageGenerationResult,
)
from .provider_registry import get_image_generation_provider, list_image_generation_providers
from .model_ref import parse_image_generation_model_ref
from .runtime_shared import (
    resolve_capability_model_candidates,
    build_no_capability_model_configured_message,
)

logger = logging.getLogger("jarvis_media.image_generation")


async def generate_image(params: GenerateImageParams) -> GenerateImageRuntimeResult:
    """Execute the image generation request with fallback looping."""

    def list_providers():
        return list_image_generation_providers(params.cfg)

    # Retrieve default image generation model config from agent config if possible
    model_config = (
        getattr(params.cfg.agents.defaults, "imageGenerationModel", None)
        if params.cfg and hasattr(params.cfg, "agents")
        else None
    )

    candidates = resolve_capability_model_candidates(
        cfg=params.cfg,
        model_config=model_config,
        model_override=params.model_override,
        parse_model_ref=parse_image_generation_model_ref,
        agent_dir=params.agent_dir,
        list_providers=list_providers,
        auto_provider_fallback=params.auto_provider_fallback,
    )

    if not candidates:
        msg = build_no_capability_model_configured_message(
            "image-generation",
            "imageGenerationModel",
            list_providers(),
        )
        raise ValueError(msg)

    attempts: list[FallbackAttempt] = []
    last_error: Optional[Exception] = None

    for candidate in candidates:
        provider_id = candidate["provider"]
        model_id = candidate["model"]

        provider = get_image_generation_provider(provider_id, params.cfg)
        if not provider:
            err_msg = f"No image-generation provider registered for {provider_id}"
            attempts.append(FallbackAttempt(provider=provider_id, model=model_id, error=err_msg))
            last_error = ValueError(err_msg)
            logger.warning(
                f"image-generation candidate failed: {provider_id}/{model_id}: {err_msg}"
            )
            continue

        input_image_count = len(params.input_images) if params.input_images else 0
        # Check max input images
        mode_capabilities = (
            provider.capabilities.edit if input_image_count else provider.capabilities.generate
        )
        max_input_images = getattr(mode_capabilities, "max_input_images", None)
        if max_input_images is not None and input_image_count > max_input_images:
            err_msg = f"{provider_id}/{model_id} supports at most {max_input_images} reference images, {input_image_count} requested"
            attempts.append(FallbackAttempt(provider=provider_id, model=model_id, error=err_msg))
            last_error = ValueError(err_msg)
            logger.warning(f"image-generation candidate skipped: {err_msg}")
            continue

        try:
            # Here we skip deep normalization logic for parity simplicity,
            # but pass raw sanitized params to provider.
            req = ImageGenerationRequest(
                provider=provider_id,
                model=model_id,
                prompt=params.prompt,
                cfg=params.cfg,
                agent_dir=params.agent_dir,
                auth_store=params.auth_store,
                count=params.count,
                size=params.size,
                aspect_ratio=params.aspect_ratio,
                resolution=params.resolution or params.inferred_resolution,
                quality=params.quality,
                output_format=params.output_format,
                background=params.background,
                input_images=params.input_images,
                timeout_ms=params.timeout_ms or provider.default_timeout_ms,
                provider_options=params.provider_options,
                ssrf_policy=params.ssrf_policy,
            )

            result: ImageGenerationResult = await provider.generate_image(req)

            if not result.images:
                raise ValueError("Image generation provider returned no images.")

            # Record success
            return GenerateImageRuntimeResult(
                images=result.images,
                provider=provider_id,
                model=result.model or model_id,
                attempts=attempts,
                metadata=result.metadata,
            )

        except Exception as err:
            last_error = err
            err_msg = str(err)
            attempts.append(FallbackAttempt(provider=provider_id, model=model_id, error=err_msg))
            logger.warning(
                f"image-generation candidate failed: {provider_id}/{model_id}: {err_msg}"
            )

    # If all candidates failed
    summary = " | ".join(f"{a.provider}/{a.model}: {a.error}" for a in attempts)
    raise RuntimeError(
        f"All image generation models failed ({len(attempts)}): {summary}"
    ) from last_error
