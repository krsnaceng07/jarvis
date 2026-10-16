"""Host CPU compute backend adapter for baseline and fallback operations."""

from __future__ import annotations

import logging
from typing import Any

from jarvis_learning.hardware.backend_adapters.base import BaseBackendAdapter
from jarvis_learning.hardware.models import MemoryAccounting

logger = logging.getLogger(__name__)


class CpuBackendAdapter(BaseBackendAdapter):
    """Executes host CPU allocations and matrix operations for fallback execution."""

    @property
    def backend_name(self) -> str:
        return "CPU"

    def is_available(self) -> bool:
        return True

    def get_device_count(self) -> int:
        return 1

    def get_memory_accounting(self, device_index: int = 0) -> MemoryAccounting:
        try:
            import psutil  # type: ignore[import-untyped]

            vm = psutil.virtual_memory()
            total = int(vm.total)
            used = int(vm.used)
            free = int(vm.available)
        except Exception:
            total = 16 * 1024 * 1024 * 1024
            used = 4 * 1024 * 1024 * 1024
            free = total - used

        return MemoryAccounting(
            total_dedicated_bytes=0,
            total_shared_bytes=total,
            device_used_bytes=used,
            device_free_bytes=free,
            process_allocated_bytes=0,
            process_reserved_bytes=0,
            external_usage_estimate_bytes=used,
        )

    def get_temperature_c(self, device_index: int = 0) -> float | None:
        # Standard host CPU temperature query without elevated hardware monitor
        return None

    def allocate_tensor(self, device_index: int, size_bytes: int) -> Any:
        try:
            import torch

            num_elements = size_bytes // 4
            return torch.empty((num_elements,), dtype=torch.float32, device="cpu")
        except Exception:
            return bytearray(size_bytes)

    def free_tensor(self, handle: Any) -> None:
        if handle is not None:
            del handle

    def synchronize(self, device_index: int) -> None:
        pass

    def execute_dummy_workload(self, device_index: int = 0) -> bool:
        try:
            import torch

            x = torch.ones((128, 128), dtype=torch.float32, device="cpu")
            y = torch.matmul(x, x)
            return float(y[0, 0].item()) > 0
        except Exception:
            # Fallback pure python matrix compute
            s = sum(i * i for i in range(1000))
            return s > 0


__all__ = ["CpuBackendAdapter"]
