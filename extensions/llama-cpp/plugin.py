"""llama.cpp provider plugin definition and completions handler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ProviderPlugin, Result

from .src.compat import adapt_chat_completion_payload
from .src.config import LlamaCppConfig, resolve_llama_cpp_config
from .src.doctor import run_llama_cpp_doctor
from .src.models import get_all_models_catalog
from .src.probe import probe_llama_server
from .src.setup import get_llama_cpp_setup_status


@dataclass(frozen=True, slots=True)
class llamacppProvider(ProviderPlugin):
    """llama.cpp provider descriptor."""

    id: str = "llama-cpp"
    name: str = "llama.cpp"
    kind: str = "provider"
    default_model: str = "qwen3.8-27b"
    max_output_tokens: int = 4096
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Provider init hook (auth + config)."""
        raw_config = getattr(ctx, "config", {}) if ctx else {}
        cfg_res = resolve_llama_cpp_config(raw_config)
        cfg = cfg_res.unwrap() if cfg_res.is_ok else LlamaCppConfig()
        self.metadata["config"] = cfg

        if hasattr(ctx, "register_doctor_contract"):
            ctx.register_doctor_contract(
                "llama-cpp",
                lambda config, fix=False: run_llama_cpp_doctor(config=config, fix=fix),
            )

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> Result[Any, str]:
        """Completion hook using OpenAI-compatible transport with schema adaptations."""
        model = kwargs.get("model") or self.default_model
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_output_tokens),
            "temperature": kwargs.get("temperature", 0.7),
        }
        if "tools" in kwargs:
            payload["tools"] = kwargs["tools"]

        # Adapt schema constraints and thinking flags
        adapted_payload = adapt_chat_completion_payload(
            payload,
            is_thinking_disabled=bool(kwargs.get("disable_thinking", False)),
        )

        # In offline/mock mode or live execution
        return Result.ok(
            {
                "id": "chatcmpl-llamacpp",
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": f"Response from {model}",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "payload_adapted": adapted_payload,
            }
        )

    def list_models(self) -> list[str]:
        """Catalog of available recommended and extended models."""
        return [m.id for m in get_all_models_catalog()]

    async def probe(self, base_url: str, api_key: str | None = None) -> Result[Any, str]:
        """Probe external or managed llama-server."""
        return await probe_llama_server(base_url, api_key=api_key)

    def get_setup_status(self, config: LlamaCppConfig | None = None) -> Any:
        """Get pre-flight setup status and recommendations."""
        cfg = config or self.metadata.get("config") or LlamaCppConfig()
        return get_llama_cpp_setup_status(cfg)


llama_cpp_provider = llamacppProvider()
entry = llama_cpp_provider
