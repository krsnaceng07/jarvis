"""NVIDIA CUDA execution adapter with PyTorch runtime and NVML telemetry."""

from __future__ import annotations

import logging
from typing import Any

from jarvis_learning.hardware.backend_adapters.base import BaseBackendAdapter
from jarvis_learning.hardware.models import MemoryAccounting

logger = logging.getLogger(__name__)


class CudaBackendAdapter(BaseBackendAdapter):
    """Executes real allocations and telemetry probes against NVIDIA CUDA devices."""

    @property
    def backend_name(self) -> str:
        return "CUDA"

    def is_available(self) -> bool:
        try:
            import torch  # type: ignore[import-untyped]

            return bool(torch.cuda.is_available())
        except Exception:
            return False

    def get_device_count(self) -> int:
        if not self.is_available():
            return 0
        import torch

        return int(torch.cuda.device_count())

    def get_memory_accounting(self, device_index: int) -> MemoryAccounting:
        if not self.is_available() or device_index >= self.get_device_count():
            return MemoryAccounting(
                total_dedicated_bytes=0,
                total_shared_bytes=0,
                device_used_bytes=0,
                device_free_bytes=0,
                process_allocated_bytes=0,
                process_reserved_bytes=0,
                external_usage_estimate_bytes=0,
            )

        import torch

        props = torch.cuda.get_device_properties(device_index)
        total = props.total_memory
        free, _ = torch.cuda.mem_get_info(device_index)
        used = total - free

        proc_allocated = torch.cuda.memory_allocated(device_index)
        proc_reserved = torch.cuda.memory_reserved(device_index)
        ext_used = max(0, used - proc_allocated)

        return MemoryAccounting(
            total_dedicated_bytes=total,
            total_shared_bytes=0,
            device_used_bytes=used,
            device_free_bytes=free,
            process_allocated_bytes=proc_allocated,
            process_reserved_bytes=proc_reserved,
            external_usage_estimate_bytes=ext_used,
        )

    def get_temperature_c(self, device_index: int) -> float | None:
        if not self.is_available():
            return None
        # Try NVML query via pynvml if installed
        try:
            import pynvml  # type: ignore[import-untyped]

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(device_index)
            temp = float(pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU))
            pynvml.nvmlShutdown()
            return temp
        except Exception:
            return None

    def allocate_tensor(self, device_index: int, size_bytes: int) -> Any:
        if not self.is_available():
            raise RuntimeError("CUDA backend is not available for tensor allocation")
        import torch

        num_elements = size_bytes // 4  # float32
        tensor = torch.empty((num_elements,), dtype=torch.float32, device=f"cuda:{device_index}")
        return tensor

    def free_tensor(self, handle: Any) -> None:
        if handle is not None:
            del handle
            try:
                import torch

                torch.cuda.empty_cache()
            except Exception:
                pass

    def synchronize(self, device_index: int) -> None:
        if self.is_available():
            import torch

            torch.cuda.synchronize(device_index)

    def execute_dummy_workload(self, device_index: int) -> bool:
        if not self.is_available():
            return False
        try:
            import torch

            x = torch.ones((1024, 1024), dtype=torch.float32, device=f"cuda:{device_index}")
            y = torch.matmul(x, x)
            self.synchronize(device_index)
            return float(y[0, 0].item()) > 0
        except Exception as exc:
            logger.debug("CUDA dummy workload failed: %s", exc)
            return False


__all__ = ["CudaBackendAdapter"]
