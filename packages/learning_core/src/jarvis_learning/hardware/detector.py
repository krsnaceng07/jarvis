"""jarvis_learning.hardware.detector — host hardware discovery.

Inspects CPU, RAM, GPU, CUDA status, and installed machine learning
libraries without crashing if optional dependencies are absent.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import platform

from .profile import ComputeProfile, ComputeTier, HardwareSpecs

logger = logging.getLogger(__name__)


class HardwareDetector:
    """Discovers host hardware and determines the active compute profile."""

    def __init__(self, override_specs: HardwareSpecs | None = None) -> None:
        self._override_specs = override_specs

    def detect_specs(self) -> HardwareSpecs:
        """Inspect the current host environment."""
        if self._override_specs is not None:
            return self._override_specs

        # 1. CPU
        cpu_threads = os.cpu_count() or 1
        # Approximate physical cores as half of logical threads on x86 hyperthreaded
        cpu_cores = max(1, cpu_threads // 2) if cpu_threads > 1 else 1

        # 2. RAM
        system_ram_gb = self._detect_ram_gb()

        # 3. Libraries
        has_torch = importlib.util.find_spec("torch") is not None
        has_transformers = importlib.util.find_spec("transformers") is not None
        has_peft = importlib.util.find_spec("peft") is not None
        has_sklearn = importlib.util.find_spec("sklearn") is not None

        # 4. GPU & CUDA
        gpu_name, has_cuda, cuda_vram_gb = self._detect_gpu(has_torch)

        return HardwareSpecs(
            cpu_cores=cpu_cores,
            cpu_threads=cpu_threads,
            system_ram_gb=round(system_ram_gb, 1),
            gpu_name=gpu_name,
            has_cuda=has_cuda,
            cuda_vram_gb=round(cuda_vram_gb, 1),
            has_torch=has_torch,
            has_transformers=has_transformers,
            has_peft=has_peft,
            has_sklearn=has_sklearn,
        )

    def determine_profile(self, specs: HardwareSpecs | None = None) -> ComputeProfile:
        """Derive the ComputeProfile from discovered hardware specs."""
        specs = specs or self.detect_specs()

        # Check library fallback first
        if not specs.has_torch and not specs.has_sklearn:
            return ComputeProfile(
                tier=ComputeTier.FALLBACK,
                specs=specs,
                recommended_batch_size=16,
                max_model_params=500_000,
                supports_quantization=False,
                supports_lora=False,
                supports_neural_training=False,
                description="Pure-Python fallback tier (no torch or scikit-learn installed)",
            )

        # CUDA Tiers
        if specs.has_cuda and specs.has_torch:
            if specs.cuda_vram_gb >= 15.0:
                return ComputeProfile(
                    tier=ComputeTier.CUDA_HIGH,
                    specs=specs,
                    recommended_batch_size=64,
                    max_model_params=14_000_000_000,
                    supports_quantization=True,
                    supports_lora=True,
                    supports_neural_training=True,
                    description=f"High-VRAM CUDA tier ({specs.cuda_vram_gb} GB VRAM)",
                )
            elif specs.cuda_vram_gb >= 7.5:
                return ComputeProfile(
                    tier=ComputeTier.CUDA_MID,
                    specs=specs,
                    recommended_batch_size=32,
                    max_model_params=7_000_000_000,
                    supports_quantization=True,
                    supports_lora=True,
                    supports_neural_training=True,
                    description=f"Mid-VRAM CUDA tier ({specs.cuda_vram_gb} GB VRAM, QLoRA)",
                )
            elif specs.cuda_vram_gb >= 3.5:
                return ComputeProfile(
                    tier=ComputeTier.CUDA_LOW,
                    specs=specs,
                    recommended_batch_size=16,
                    max_model_params=3_000_000_000,
                    supports_quantization=True,
                    supports_lora=True,
                    supports_neural_training=True,
                    description=f"Low-VRAM CUDA tier ({specs.cuda_vram_gb} GB VRAM, QLoRA with CPU offload)",
                )

        # CPU Tiers
        if specs.system_ram_gb >= 15.0:
            return ComputeProfile(
                tier=ComputeTier.CPU_MEMORY_RICH,
                specs=specs,
                recommended_batch_size=16,
                max_model_params=20_000_000,
                supports_quantization=False,
                supports_lora=False,
                supports_neural_training=specs.has_torch,
                description=(
                    f"CPU High-Memory tier ({specs.system_ram_gb} GB RAM, "
                    f"{specs.cpu_cores}C/{specs.cpu_threads}T CPU, small models/linear baselines)"
                ),
            )

        return ComputeProfile(
            tier=ComputeTier.CPU_LIMITED,
            specs=specs,
            recommended_batch_size=8,
            max_model_params=5_000_000,
            supports_quantization=False,
            supports_lora=False,
            supports_neural_training=specs.has_torch,
            description=f"CPU-Limited tier ({specs.system_ram_gb} GB RAM, small linear/feature models)",
        )

    # ── Internal Discovery Helpers ────────────────────────────

    @staticmethod
    def _detect_ram_gb() -> float:
        """Detect system physical RAM in gigabytes."""
        try:
            if platform.system() == "Windows":
                import ctypes

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                    return stat.ullTotalPhys / (1024**3)
            elif platform.system() == "Linux":
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            parts = line.split()
                            return int(parts[1]) / (1024**2)
        except Exception as e:
            logger.debug("Failed to detect physical RAM directly: %s", e)
        return 8.0  # Safe default fallback

    @staticmethod
    def _detect_gpu(has_torch: bool) -> tuple[str, bool, float]:
        """Detect GPU name, CUDA presence, and VRAM in GB."""
        if has_torch:
            try:
                import torch

                if torch.cuda.is_available():
                    gpu_name = torch.cuda.get_device_name(0)
                    props = torch.cuda.get_device_properties(0)
                    vram_gb = getattr(props, "total_memory", 0) / (1024**3)
                    return gpu_name, True, vram_gb
            except Exception as e:
                logger.debug("Torch CUDA query failed: %s", e)

        # Fallback inspection on Windows using environment / video controller
        gpu_name = "Integrated / Generic Display Adapter"
        if platform.system() == "Windows":
            try:
                import subprocess

                res = subprocess.run(
                    ["powershell", "-Command", "(Get-CimInstance Win32_VideoController).Name"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if res.returncode == 0 and res.stdout.strip():
                    first_line = res.stdout.strip().splitlines()[0].strip()
                    if first_line:
                        gpu_name = first_line
            except Exception:
                pass

        return gpu_name, False, 0.0
