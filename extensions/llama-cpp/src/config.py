"""Configuration definitions and resolver for the llama.cpp provider plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Err, Ok, Result


@dataclass(slots=True)
class LlamaCppLocalServiceConfig:
    """Settings for managed local llama-server instance."""

    model_path: str = ""
    context_size: int = 65536
    threads: int | None = None
    gpu_layers: int | None = None
    download_dir: str | None = None
    embedding_only: bool = False


@dataclass(slots=True)
class LlamaCppModelConfig:
    """Individual configured or discovered model entry."""

    id: str
    name: str = ""
    model_path: str = ""
    context_window: int = 65536
    max_tokens: int = 4096
    supports_tools: bool = True
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LlamaCppConfig:
    """Root configuration for llama.cpp model provider."""

    enabled: bool = True
    base_url: str = "http://127.0.0.1:8080/v1"
    api: str = "openai-completions"
    api_key: str | None = None
    local_service: LlamaCppLocalServiceConfig | None = None
    models: list[LlamaCppModelConfig] = field(default_factory=list)
    default_model: str = "qwen3.8-27b"
    max_output_tokens: int = 4096
    model_cache_dir: str = "~/.openclaw/models/llama.cpp"
    allow_private_network: bool = True

    @property
    def is_managed(self) -> bool:
        """Return True if OpenClaw manages the local llama-server process."""
        return self.local_service is not None


def resolve_llama_cpp_config(
    raw_config: dict[str, Any] | None,
) -> Result[LlamaCppConfig, str]:
    """Parse and resolve raw llama-cpp provider configuration."""
    if not raw_config:
        return Ok(LlamaCppConfig())

    try:
        enabled = bool(raw_config.get("enabled", True))
        base_url = str(
            raw_config.get("baseUrl") or raw_config.get("base_url") or "http://127.0.0.1:8080/v1"
        )
        api = str(raw_config.get("api") or "openai-completions")
        api_key = raw_config.get("apiKey") or raw_config.get("api_key")
        default_model = str(
            raw_config.get("defaultModel") or raw_config.get("default_model") or "qwen3.8-27b"
        )
        max_output_tokens = int(
            raw_config.get("maxOutputTokens") or raw_config.get("max_output_tokens") or 4096
        )
        cache_dir = str(
            raw_config.get("modelCacheDir")
            or raw_config.get("model_cache_dir")
            or "~/.openclaw/models/llama.cpp"
        )

        # Parse local_service if present (Managed mode)
        raw_local = raw_config.get("localService") or raw_config.get("local_service")
        local_service: LlamaCppLocalServiceConfig | None = None
        if raw_local and isinstance(raw_local, dict):
            local_service = LlamaCppLocalServiceConfig(
                model_path=str(raw_local.get("modelPath") or raw_local.get("model_path") or ""),
                context_size=int(
                    raw_local.get("contextSize") or raw_local.get("context_size") or 65536
                ),
                threads=raw_local.get("threads"),
                gpu_layers=raw_local.get("gpuLayers") or raw_local.get("gpu_layers"),
                download_dir=raw_local.get("downloadDir") or raw_local.get("download_dir"),
                embedding_only=bool(
                    raw_local.get("embeddingOnly") or raw_local.get("embedding_only", False)
                ),
            )

        # Parse models list
        raw_models = raw_config.get("models") or []
        model_configs: list[LlamaCppModelConfig] = []
        if isinstance(raw_models, list):
            for m in raw_models:
                if isinstance(m, dict):
                    m_id = str(m.get("id") or "")
                    if m_id:
                        compat = m.get("compat") or {}
                        model_configs.append(
                            LlamaCppModelConfig(
                                id=m_id,
                                name=str(m.get("name") or m_id),
                                model_path=str(
                                    m.get("modelPath") or m.get("params", {}).get("modelPath") or ""
                                ),
                                context_window=int(m.get("contextWindow") or 65536),
                                max_tokens=int(m.get("maxTokens") or 4096),
                                supports_tools=bool(compat.get("supportsTools", True)),
                                params=dict(m.get("params") or {}),
                            )
                        )

        return Ok(
            LlamaCppConfig(
                enabled=enabled,
                base_url=base_url,
                api=api,
                api_key=api_key,
                local_service=local_service,
                models=model_configs,
                default_model=default_model,
                max_output_tokens=max_output_tokens,
                model_cache_dir=cache_dir,
            )
        )
    except Exception as ex:
        return Err(f"Failed to resolve llama.cpp config: {ex}")
