"""
Runtime entrypoint for video generation with provider fallback.
"""

from typing import Optional
import logging

from .types import (
    GenerateVideoParams,
    GenerateVideoRuntimeResult,
    FallbackAttempt,
    VideoGenerationRequest,
    VideoGenerationResult,
)
from .provider_registry import get_video_generation_provider, list_video_generation_providers
from jarvis_media.image_generation.runtime_shared import (
    resolve_capability_model_candidates,
    build_no_capability_model_configured_message,
)

logger = logging.getLogger("jarvis_media.video_generation")


def parse_video_generation_model_ref(model_ref: Optional[str]) -> Optional[dict[str, str]]:
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


async def generate_video(params: GenerateVideoParams) -> GenerateVideoRuntimeResult:
    """Execute the video generation request with fallback looping."""

    def list_providers():
        return list_video_generation_providers(params.cfg)

    model_config = (
        getattr(params.cfg.agents.defaults, "videoGenerationModel", None)
        if params.cfg and hasattr(params.cfg, "agents")
        else None
    )

    candidates = resolve_capability_model_candidates(
        cfg=params.cfg,
        model_config=model_config,
        model_override=params.model_override,
        parse_model_ref=parse_video_generation_model_ref,
        agent_dir=params.agent_dir,
        list_providers=list_providers,
        auto_provider_fallback=params.auto_provider_fallback,
    )

    if not candidates:
        msg = build_no_capability_model_configured_message(
            "video-generation",
            "videoGenerationModel",
            list_providers(),
        )
        raise ValueError(msg)

    attempts: list[FallbackAttempt] = []
    last_error: Optional[Exception] = None

    for candidate in candidates:
        provider_id = candidate["provider"]
        model_id = candidate["model"]

        provider = get_video_generation_provider(provider_id, params.cfg)
        if not provider:
            err_msg = f"No video-generation provider registered for {provider_id}"
            attempts.append(FallbackAttempt(provider=provider_id, model=model_id, error=err_msg))
            last_error = ValueError(err_msg)
            logger.warning(
                f"video-generation candidate failed: {provider_id}/{model_id}: {err_msg}"
            )
            continue

        try:
            req = VideoGenerationRequest(
                provider=provider_id,
                model=model_id,
                prompt=params.prompt,
                cfg=params.cfg,
                agent_dir=params.agent_dir,
                auth_store=params.auth_store,
                aspect_ratio=params.aspect_ratio,
                resolution=params.resolution,
                duration_seconds=params.duration_seconds,
                fps=params.fps,
                input_images=params.input_images,
                input_video=params.input_video,
                timeout_ms=params.timeout_ms or provider.default_timeout_ms,
                provider_options=params.provider_options,
                ssrf_policy=params.ssrf_policy,
            )

            result: VideoGenerationResult = await provider.generate_video(req)

            if not result.videos:
                raise ValueError("Video generation provider returned no videos.")

            return GenerateVideoRuntimeResult(
                videos=result.videos,
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
                f"video-generation candidate failed: {provider_id}/{model_id}: {err_msg}"
            )

    summary = " | ".join(f"{a.provider}/{a.model}: {a.error}" for a in attempts)
    raise RuntimeError(
        f"All video generation models failed ({len(attempts)}): {summary}"
    ) from last_error
