"""jarvis.plugins.llama_cpp — llama.cpp provider plugin & local GGUF model configuration.

OpenClaw parity: mirrors
``openclaw-main/extensions/llama-cpp/src/defaults.ts`` and
``openclaw-main/extensions/llama-cpp/index.ts``.

Features:
- `LLAMA_CPP_PROVIDER_ID`: `"llama-cpp"`
- `LLAMA_CPP_PROVIDER_LABEL`: `"Local model (llama.cpp)"`
- `LLAMA_CPP_LOCAL_AUTH_MARKER`: `"llama-cpp-local"`
- `LLAMA_CPP_LOCAL_BASE_URL`: `"local://llama-cpp"`
- `DEFAULT_LLAMA_CPP_MODEL_ID`: `"gemma-4-e4b-it-q4_k_m"`
- `DEFAULT_LLAMA_CPP_MODEL_REF`: `"llama-cpp/gemma-4-e4b-it-q4_k_m"`
- `DEFAULT_LLAMA_CPP_MODEL_URI`: `"hf:unsloth/gemma-4-E4B-it-GGUF/gemma-4-E4B-it-Q4_K_M.gguf"`
- `DEFAULT_LLAMA_CPP_EMBEDDING_MODEL_URI`: `"hf:ggml-org/embeddinggemma-300m-qat-q8_0-GGUF/embeddinggemma-300m-qat-Q8_0.gguf"`
- `DEFAULT_LLAMA_CPP_MODEL_SIZE_BYTES`: `4_977_169_568`
- `DEFAULT_LLAMA_CPP_CONTEXT_SIZE`: `8192`
- `LLAMA_CPP_RAM_FLOOR_BYTES`: `17_179_869_184` (16 GiB)
- `meets_llama_cpp_ram_floor()`: Evaluates total RAM against 16 GiB floor.
- `resolve_llama_cpp_model_cache_dir()`: Resolves model cache directory.
- `LlamaCppModelConfig`: Dataclass containing model configuration options.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LLAMA_CPP_PROVIDER_ID: str = "llama-cpp"
LLAMA_CPP_PROVIDER_LABEL: str = "Local model (llama.cpp)"
LLAMA_CPP_LOCAL_AUTH_MARKER: str = "llama-cpp-local"
LLAMA_CPP_LOCAL_BASE_URL: str = "local://llama-cpp"

DEFAULT_LLAMA_CPP_MODEL_ID: str = "gemma-4-e4b-it-q4_k_m"
DEFAULT_LLAMA_CPP_MODEL_REF: str = f"{LLAMA_CPP_PROVIDER_ID}/{DEFAULT_LLAMA_CPP_MODEL_ID}"
DEFAULT_LLAMA_CPP_MODEL_URI: str = (
    "hf:unsloth/gemma-4-E4B-it-GGUF/gemma-4-E4B-it-Q4_K_M.gguf"
)
DEFAULT_LLAMA_CPP_EMBEDDING_MODEL_URI: str = (
    "hf:ggml-org/embeddinggemma-300m-qat-q8_0-GGUF/embeddinggemma-300m-qat-Q8_0.gguf"
)
DEFAULT_LLAMA_CPP_MODEL_SIZE_BYTES: int = 4_977_169_568
DEFAULT_LLAMA_CPP_CONTEXT_SIZE: int = 8192

LLAMA_CPP_RAM_FLOOR_BYTES: int = 16 * 1024 * 1024 * 1024  # 16 GiB


def meets_llama_cpp_ram_floor(total_ram_bytes: int) -> bool:
    """Check if total RAM meets or exceeds the 16 GiB floor required for default GGUF."""
    return total_ram_bytes >= LLAMA_CPP_RAM_FLOOR_BYTES


def resolve_llama_cpp_model_cache_dir(custom_path: str | None = None) -> str:
    """Resolve model cache directory path with ~ expansion."""
    if custom_path and isinstance(custom_path, str) and custom_path.strip():
        p = custom_path.strip()
        return str(Path(os.path.expanduser(p)).resolve())
    return str(Path(os.path.expanduser("~/.jarvis/models/llama.cpp")).resolve())


@dataclass
class LlamaCppModelConfig:
    id: str = DEFAULT_LLAMA_CPP_MODEL_ID
    model_path: str = DEFAULT_LLAMA_CPP_MODEL_URI
    context_size: int = DEFAULT_LLAMA_CPP_CONTEXT_SIZE
    supports_tools: bool = True


def resolve_llama_cpp_model_config(model_cfg: dict[str, Any] | None) -> LlamaCppModelConfig:
    """Resolve Llama.cpp model options from model dictionary."""
    val = model_cfg if isinstance(model_cfg, dict) else {}
    params = val.get("params") if isinstance(val.get("params"), dict) else {}

    model_id = str(val.get("id") or DEFAULT_LLAMA_CPP_MODEL_ID).strip()
    model_path = str(params.get("modelPath") or DEFAULT_LLAMA_CPP_MODEL_URI).strip()
    ctx_size = int(params.get("contextSize", DEFAULT_LLAMA_CPP_CONTEXT_SIZE))

    compat = val.get("compat") if isinstance(val.get("compat"), dict) else {}
    supports_tools = bool(compat.get("supportsTools", True))

    return LlamaCppModelConfig(
        id=model_id,
        model_path=model_path,
        context_size=ctx_size,
        supports_tools=supports_tools,
    )


__all__ = [
    "DEFAULT_LLAMA_CPP_CONTEXT_SIZE",
    "DEFAULT_LLAMA_CPP_EMBEDDING_MODEL_URI",
    "DEFAULT_LLAMA_CPP_MODEL_ID",
    "DEFAULT_LLAMA_CPP_MODEL_REF",
    "DEFAULT_LLAMA_CPP_MODEL_SIZE_BYTES",
    "DEFAULT_LLAMA_CPP_MODEL_URI",
    "LLAMA_CPP_LOCAL_AUTH_MARKER",
    "LLAMA_CPP_LOCAL_BASE_URL",
    "LLAMA_CPP_PROVIDER_ID",
    "LLAMA_CPP_PROVIDER_LABEL",
    "LLAMA_CPP_RAM_FLOOR_BYTES",
    "LlamaCppModelConfig",
    "meets_llama_cpp_ram_floor",
    "resolve_llama_cpp_model_cache_dir",
    "resolve_llama_cpp_model_config",
]
