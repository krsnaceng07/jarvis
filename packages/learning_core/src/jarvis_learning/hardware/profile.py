"""jarvis_learning.hardware.profile — compute tiers and hardware profiles.

Defines compute tiers, hardware specifications, and device capability
profiles for JARVIS learning workloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ComputeTier(StrEnum):
    """Execution tiers derived from host hardware and installed libraries."""

    CUDA_HIGH = "cuda_high"  # >= 16 GB CUDA VRAM (PEFT/LoRA 7B/8B)
    CUDA_MID = "cuda_mid"  # 8-16 GB CUDA VRAM (QLoRA 4-bit)
    CUDA_LOW = "cuda_low"  # 4-8 GB CUDA VRAM (QLoRA + CPU offload)
    CPU_MEMORY_RICH = "cpu_memory_rich"  # No CUDA, >= 16 GB RAM (Host machine profile)
    CPU_LIMITED = "cpu_limited"  # No CUDA, < 16 GB RAM
    FALLBACK = "fallback"  # Missing torch/ml dependencies (pure-Python)


@dataclass(frozen=True, slots=True)
class HardwareSpecs:
    """Raw hardware parameters discovered on the host."""

    cpu_cores: int
    cpu_threads: int
    system_ram_gb: float
    gpu_name: str
    has_cuda: bool
    cuda_vram_gb: float
    has_torch: bool
    has_transformers: bool
    has_peft: bool
    has_sklearn: bool


@dataclass(frozen=True, slots=True)
class ComputeProfile:
    """Operational capability profile for model training and inference."""

    tier: ComputeTier
    specs: HardwareSpecs
    recommended_batch_size: int
    max_model_params: int
    supports_quantization: bool
    supports_lora: bool
    supports_neural_training: bool
    description: str

    def can_train_target(self, target: str) -> bool:
        """Check if this compute profile can train a given target."""
        if self.tier == ComputeTier.FALLBACK:
            # Fallback supports pure-python models for all targets
            return True
        return True
