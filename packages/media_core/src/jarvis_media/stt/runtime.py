"""
Runtime entrypoint for STT with provider fallback.
"""

from typing import Optional
import logging

from .types import (
    GenerateSttParams,
    GenerateSttRuntimeResult,
    SttRequest,
    SttResult,
)
from jarvis_media.image_generation.types import FallbackAttempt
from .provider_registry import get_stt_provider, list_stt_providers
from jarvis_media.image_generation.runtime_shared import (
    resolve_capability_model_candidates,
    build_no_capability_model_configured_message,
)

logger = logging.getLogger("jarvis_media.stt")


def parse_stt_model_ref(model_ref: Optional[str]) -> Optional[dict[str, str]]:
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


async def transcribe_audio(params: GenerateSttParams) -> GenerateSttRuntimeResult:
    """Execute the STT request with fallback looping."""

    def list_providers():
        return list_stt_providers(params.cfg)

    model_config = (
        getattr(params.cfg.agents.defaults, "sttModel", None)
        if params.cfg and hasattr(params.cfg, "agents")
        else None
    )

    candidates = resolve_capability_model_candidates(
        cfg=params.cfg,
        model_config=model_config,
        model_override=params.model_override,
        parse_model_ref=parse_stt_model_ref,
        agent_dir=params.agent_dir,
        list_providers=list_providers,
        auto_provider_fallback=params.auto_provider_fallback,
    )

    if not candidates:
        msg = build_no_capability_model_configured_message(
            "stt",
            "sttModel",
            list_providers(),
        )
        raise ValueError(msg)

    attempts: list[FallbackAttempt] = []
    last_error: Optional[Exception] = None

    for candidate in candidates:
        provider_id = candidate["provider"]
        model_id = candidate["model"]

        provider = get_stt_provider(provider_id, params.cfg)
        if not provider:
            err_msg = f"No STT provider registered for {provider_id}"
            attempts.append(FallbackAttempt(provider=provider_id, model=model_id, error=err_msg))
            last_error = ValueError(err_msg)
            logger.warning(f"stt candidate failed: {provider_id}/{model_id}: {err_msg}")
            continue

        try:
            req = SttRequest(
                provider=provider_id,
                model=model_id,
                audio_base64=params.audio_base64,
                audio_url=params.audio_url,
                audio_mime_type=params.audio_mime_type,
                language=params.language,
                cfg=params.cfg,
                agent_dir=params.agent_dir,
                auth_store=params.auth_store,
                timeout_ms=params.timeout_ms or provider.default_timeout_ms,
                provider_options=params.provider_options,
                ssrf_policy=params.ssrf_policy,
            )

            result: SttResult = await provider.transcribe_audio(req)

            if not result.text:
                raise ValueError("STT provider returned empty text.")

            return GenerateSttRuntimeResult(
                text=result.text,
                provider=provider_id,
                model=result.model or model_id,
                language=result.language,
                metadata=result.metadata,
            )

        except Exception as err:
            last_error = err
            err_msg = str(err)
            attempts.append(FallbackAttempt(provider=provider_id, model=model_id, error=err_msg))
            logger.warning(f"stt candidate failed: {provider_id}/{model_id}: {err_msg}")

    summary = " | ".join(f"{a.provider}/{a.model}: {a.error}" for a in attempts)
    raise RuntimeError(f"All STT models failed ({len(attempts)}): {summary}") from last_error
