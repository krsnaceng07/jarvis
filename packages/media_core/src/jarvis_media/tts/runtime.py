"""
Runtime entrypoint for TTS with provider fallback.
"""

from typing import Optional
import logging

from .types import (
    GenerateTtsParams,
    GenerateTtsRuntimeResult,
    TtsRequest,
    TtsResult,
)
from jarvis_media.image_generation.types import FallbackAttempt
from .provider_registry import get_tts_provider, list_tts_providers
from jarvis_media.image_generation.runtime_shared import (
    resolve_capability_model_candidates,
    build_no_capability_model_configured_message,
)

logger = logging.getLogger("jarvis_media.tts")


def parse_tts_model_ref(model_ref: Optional[str]) -> Optional[dict[str, str]]:
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


async def generate_tts(params: GenerateTtsParams) -> GenerateTtsRuntimeResult:
    """Execute the TTS request with fallback looping."""

    def list_providers():
        return list_tts_providers(params.cfg)

    model_config = (
        getattr(params.cfg.agents.defaults, "ttsModel", None)
        if params.cfg and hasattr(params.cfg, "agents")
        else None
    )

    candidates = resolve_capability_model_candidates(
        cfg=params.cfg,
        model_config=model_config,
        model_override=params.model_override,
        parse_model_ref=parse_tts_model_ref,
        agent_dir=params.agent_dir,
        list_providers=list_providers,
        auto_provider_fallback=params.auto_provider_fallback,
    )

    if not candidates:
        msg = build_no_capability_model_configured_message(
            "tts",
            "ttsModel",
            list_providers(),
        )
        raise ValueError(msg)

    attempts: list[FallbackAttempt] = []
    last_error: Optional[Exception] = None

    for candidate in candidates:
        provider_id = candidate["provider"]
        model_id = candidate["model"]

        provider = get_tts_provider(provider_id, params.cfg)
        if not provider:
            err_msg = f"No TTS provider registered for {provider_id}"
            attempts.append(FallbackAttempt(provider=provider_id, model=model_id, error=err_msg))
            last_error = ValueError(err_msg)
            logger.warning(f"tts candidate failed: {provider_id}/{model_id}: {err_msg}")
            continue

        try:
            req = TtsRequest(
                provider=provider_id,
                model=model_id,
                text=params.text,
                voice=params.voice_override or provider.default_voice,
                cfg=params.cfg,
                agent_dir=params.agent_dir,
                auth_store=params.auth_store,
                speed=params.speed,
                pitch=params.pitch,
                output_format=params.output_format,
                timeout_ms=params.timeout_ms or provider.default_timeout_ms,
                provider_options=params.provider_options,
                ssrf_policy=params.ssrf_policy,
            )

            result: TtsResult = await provider.generate_tts(req)

            if not result.audio:
                raise ValueError("TTS provider returned no audio.")

            return GenerateTtsRuntimeResult(
                audio=result.audio,
                provider=provider_id,
                model=result.model or model_id,
                voice=result.voice or req.voice,
                metadata=result.metadata,
            )

        except Exception as err:
            last_error = err
            err_msg = str(err)
            attempts.append(FallbackAttempt(provider=provider_id, model=model_id, error=err_msg))
            logger.warning(f"tts candidate failed: {provider_id}/{model_id}: {err_msg}")

    summary = " | ".join(f"{a.provider}/{a.model}: {a.error}" for a in attempts)
    raise RuntimeError(f"All TTS models failed ({len(attempts)}): {summary}") from last_error
