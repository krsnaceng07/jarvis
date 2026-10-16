"""llama.cpp pinned model catalog, download specifications, and hardware recommendation engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class LlamaCppModelSpec:
    id: str
    name: str
    family: str
    download_size_gb: float
    min_host_memory_gib: float
    requires_gpu: bool
    context_window: int = 65536
    max_output_tokens: int = 4096
    supports_tools: bool = True
    hf_repo: str = ""
    hf_file: str = ""
    quantization: str = "Q4_K_M"
    extra_params: dict[str, Any] = field(default_factory=dict)


# Pinned Text-Only Recommendation Catalog (in prioritized recommendation order)
RECOMMENDED_MODELS: list[LlamaCppModelSpec] = [
    LlamaCppModelSpec(
        id="qwen3.8-27b",
        name="Qwen3.8 27B UD-Q4_K_M",
        family="qwen",
        download_size_gb=16.5,
        min_host_memory_gib=32.0,
        requires_gpu=True,
        hf_repo="Qwen/Qwen3.8-27B-Instruct-GGUF",
        hf_file="qwen3.8-27b-instruct-ud-q4_k_m.gguf",
    ),
    LlamaCppModelSpec(
        id="muse-glimmer-30b",
        name="Muse Glimmer 30B Q4_K_M",
        family="muse",
        download_size_gb=16.8,
        min_host_memory_gib=32.0,
        requires_gpu=True,
        hf_repo="muse-glimmer/Muse-Glimmer-30B-GGUF",
        hf_file="muse-glimmer-30b-q4_k_m.gguf",
        extra_params={"fits_24gb_vram": True},
    ),
    LlamaCppModelSpec(
        id="gemma4-12b",
        name="Gemma 4 12B IT Q4_K_M",
        family="gemma",
        download_size_gb=7.1,
        min_host_memory_gib=24.0,
        requires_gpu=True,
        hf_repo="google/gemma-4-12b-it-GGUF",
        hf_file="gemma-4-12b-it-q4_k_m.gguf",
    ),
    LlamaCppModelSpec(
        id="qwen3.5-9b",
        name="Qwen3.5 9B Q4_K_M",
        family="qwen",
        download_size_gb=5.7,
        min_host_memory_gib=16.0,
        requires_gpu=False,
        hf_repo="Qwen/Qwen3.5-9B-Instruct-GGUF",
        hf_file="qwen3.5-9b-instruct-q4_k_m.gguf",
    ),
    LlamaCppModelSpec(
        id="qwen3.5-4b",
        name="Qwen3.5 4B Q4_K_M",
        family="qwen",
        download_size_gb=2.7,
        min_host_memory_gib=8.0,
        requires_gpu=False,
        hf_repo="Qwen/Qwen3.5-4B-Instruct-GGUF",
        hf_file="qwen3.5-4b-instruct-q4_k_m.gguf",
    ),
]

# Additional Historical Catalog Models for Existing Routes
EXTENDED_CATALOG_MODELS: list[LlamaCppModelSpec] = [
    LlamaCppModelSpec(
        id="gemma4-e2b",
        name="Gemma 4 E2B IT",
        family="gemma",
        download_size_gb=1.5,
        min_host_memory_gib=4.0,
        requires_gpu=False,
        context_window=32768,
    ),
    LlamaCppModelSpec(
        id="gemma4-e4b",
        name="Gemma 4 E4B IT",
        family="gemma",
        download_size_gb=2.9,
        min_host_memory_gib=8.0,
        requires_gpu=False,
        context_window=65536,
    ),
    LlamaCppModelSpec(
        id="gemma4-26b-a4b",
        name="Gemma 4 26B A4B IT",
        family="gemma",
        download_size_gb=15.2,
        min_host_memory_gib=32.0,
        requires_gpu=True,
        context_window=65536,
    ),
]

DEFAULT_EMBEDDING_MODEL = LlamaCppModelSpec(
    id="embeddinggemma-300m",
    name="EmbeddingGemma 300M QAT Q8_0",
    family="embeddinggemma",
    download_size_gb=0.3,
    min_host_memory_gib=1.0,
    requires_gpu=False,
    context_window=2048,
    max_output_tokens=0,
    supports_tools=False,
    hf_repo="ggml-org/embeddinggemma-300m-qat-q8_0-GGUF",
    hf_file="embeddinggemma-300m-qat-Q8_0.gguf",
)


@dataclass(slots=True)
class HardwareMetrics:
    ram_gib: float
    free_ram_gib: float
    has_gpu: bool
    gpu_type: str = "cpu"  # "cuda", "metal", "cpu"
    vram_gib: float = 0.0
    free_disk_gb: float = 50.0


def recommend_model_for_hardware(metrics: HardwareMetrics) -> LlamaCppModelSpec | None:
    """Recommend the optimal model recipe for the Gateway host's available hardware.

    Accounting for:
    - OS and runtime headroom (~3-4 GiB RAM reserve)
    - GPU acceleration availability and VRAM budgets
    - Free disk storage (download size + embedding model + 5 GB staging)
    """
    total_effective_ram = metrics.ram_gib
    has_gpu_accel = metrics.has_gpu and metrics.gpu_type in ("cuda", "metal")

    for model in RECOMMENDED_MODELS:
        # Check GPU constraint
        if model.requires_gpu and not has_gpu_accel:
            continue

        # Check VRAM constraint for large models if dedicated VRAM is reported
        if model.requires_gpu and metrics.vram_gib > 0:
            if model.id == "qwen3.8-27b" and metrics.vram_gib < 24.0:
                continue
            if model.id == "muse-glimmer-30b" and metrics.vram_gib < 20.0:
                continue
            if model.id == "gemma4-12b" and metrics.vram_gib < 12.0:
                continue

        # Check Host RAM constraint
        if total_effective_ram < model.min_host_memory_gib:
            continue

        # Check Free Disk Space (model download + embedding ~0.3 GB + 3 GB staging buffer)
        required_disk = model.download_size_gb + DEFAULT_EMBEDDING_MODEL.download_size_gb + 3.0
        if metrics.free_disk_gb < required_disk:
            continue

        return model

    return None


def get_all_models_catalog() -> list[LlamaCppModelSpec]:
    """Return complete list of all recommended and extended models."""
    return RECOMMENDED_MODELS + EXTENDED_CATALOG_MODELS
