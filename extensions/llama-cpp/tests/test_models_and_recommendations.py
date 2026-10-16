"""Unit tests for llama.cpp model catalog, specs, and hardware recommendation logic."""

from __future__ import annotations

from extensions.llama_cpp.src.models import (
    DEFAULT_EMBEDDING_MODEL,
    HardwareMetrics,
    get_all_models_catalog,
    recommend_model_for_hardware,
)


def test_model_catalog_structure() -> None:
    catalog = get_all_models_catalog()
    assert len(catalog) >= 5

    # Check top recommendations exist
    model_ids = [m.id for m in catalog]
    assert "qwen3.8-27b" in model_ids
    assert "muse-glimmer-30b" in model_ids
    assert "gemma4-12b" in model_ids
    assert "qwen3.5-9b" in model_ids
    assert "qwen3.5-4b" in model_ids

    # Embedding model specification
    assert DEFAULT_EMBEDDING_MODEL.id == "embeddinggemma-300m"
    assert DEFAULT_EMBEDDING_MODEL.download_size_gb <= 0.5


def test_hardware_recommendation_gpu_high_end() -> None:
    # 1. 32 GiB RAM + 24 GiB NVIDIA GPU -> Qwen3.8 27B
    metrics_32gb = HardwareMetrics(
        ram_gib=32.0,
        free_ram_gib=28.0,
        has_gpu=True,
        gpu_type="cuda",
        vram_gib=24.0,
        free_disk_gb=100.0,
    )
    rec1 = recommend_model_for_hardware(metrics_32gb)
    assert rec1 is not None
    assert rec1.id == "qwen3.8-27b"

    # 2. 32 GiB RAM + 20 GiB GPU (smaller context cache fits Muse)
    metrics_muse = HardwareMetrics(
        ram_gib=32.0,
        free_ram_gib=28.0,
        has_gpu=True,
        gpu_type="cuda",
        vram_gib=20.0,
        free_disk_gb=100.0,
    )
    rec2 = recommend_model_for_hardware(metrics_muse)
    assert rec2 is not None
    assert rec2.id == "muse-glimmer-30b"

    # 3. 24 GiB RAM + 16 GiB GPU -> Gemma 4 12B
    metrics_24gb = HardwareMetrics(
        ram_gib=24.0,
        free_ram_gib=20.0,
        has_gpu=True,
        gpu_type="cuda",
        vram_gib=16.0,
        free_disk_gb=50.0,
    )
    rec3 = recommend_model_for_hardware(metrics_24gb)
    assert rec3 is not None
    assert rec3.id == "gemma4-12b"


def test_hardware_recommendation_cpu_limits() -> None:
    # 1. 16 GiB RAM CPU-only -> Qwen3.5 9B (CPU recommendation limit)
    metrics_cpu_16gb = HardwareMetrics(
        ram_gib=16.0,
        free_ram_gib=14.0,
        has_gpu=False,
        gpu_type="cpu",
        free_disk_gb=50.0,
    )
    rec_cpu = recommend_model_for_hardware(metrics_cpu_16gb)
    assert rec_cpu is not None
    assert rec_cpu.id == "qwen3.5-9b"

    # 2. 8 GiB RAM CPU-only -> Qwen3.5 4B
    metrics_cpu_8gb = HardwareMetrics(
        ram_gib=8.0,
        free_ram_gib=6.0,
        has_gpu=False,
        gpu_type="cpu",
        free_disk_gb=30.0,
    )
    rec_8gb = recommend_model_for_hardware(metrics_cpu_8gb)
    assert rec_8gb is not None
    assert rec_8gb.id == "qwen3.5-4b"

    # 3. Low RAM (< 8 GiB) -> None
    metrics_low_ram = HardwareMetrics(
        ram_gib=4.0,
        free_ram_gib=3.0,
        has_gpu=False,
        gpu_type="cpu",
        free_disk_gb=30.0,
    )
    assert recommend_model_for_hardware(metrics_low_ram) is None

    # 4. Low Disk (< required download) -> None
    metrics_low_disk = HardwareMetrics(
        ram_gib=16.0,
        free_ram_gib=14.0,
        has_gpu=False,
        gpu_type="cpu",
        free_disk_gb=2.0,
    )
    assert recommend_model_for_hardware(metrics_low_disk) is None
