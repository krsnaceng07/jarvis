"""Accelerator backend adapters for hardware validation."""

from __future__ import annotations

from jarvis_learning.hardware.backend_adapters.base import BaseBackendAdapter
from jarvis_learning.hardware.backend_adapters.cpu_adapter import CpuBackendAdapter
from jarvis_learning.hardware.backend_adapters.cuda_adapter import CudaBackendAdapter
from jarvis_learning.hardware.backend_adapters.directml_adapter import DirectMLBackendAdapter

__all__ = [
    "BaseBackendAdapter",
    "CpuBackendAdapter",
    "CudaBackendAdapter",
    "DirectMLBackendAdapter",
]
