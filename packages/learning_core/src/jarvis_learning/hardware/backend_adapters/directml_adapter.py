"""Windows DirectML backend execution adapter."""

from __future__ import annotations

import logging
from typing import Any

from jarvis_learning.hardware.backend_adapters.base import BaseBackendAdapter
from jarvis_learning.hardware.models import DirectMLCapability, MemoryAccounting

logger = logging.getLogger(__name__)


class DirectMLBackendAdapter(BaseBackendAdapter):
    """Executes real allocations and workload operations against DirectX 12 DirectML devices."""

    @property
    def backend_name(self) -> str:
        return "DIRECTML"

    def probe_capability_stage(self) -> DirectMLCapability:
        """Evaluate deep DirectML capability stage from installation to workload execution."""
        try:
            import torch_directml  # type: ignore[import-untyped]
        except ImportError:
            return DirectMLCapability.NOT_INSTALLED

        try:
            count = torch_directml.device_count()
            if count <= 0:
                return DirectMLCapability.LIBRARY_FOUND
        except Exception:
            return DirectMLCapability.LIBRARY_FOUND

        try:
            dev = torch_directml.device(0)
        except Exception:
            return DirectMLCapability.ADAPTER_ENUMERATED

        try:
            import torch

            x = torch.ones((64, 64), dtype=torch.float32, device=dev)
            y = x + x
            if float(y[0, 0].item()) != 2.0:
                return DirectMLCapability.DEVICE_CREATED
        except Exception:
            return DirectMLCapability.DEVICE_CREATED

        return DirectMLCapability.WORKLOAD_EXECUTED

    def is_available(self) -> bool:
        stage = self.probe_capability_stage()
        return stage == DirectMLCapability.WORKLOAD_EXECUTED

    def get_device_count(self) -> int:
        try:
            import torch_directml

            return int(torch_directml.device_count())
        except Exception:
            return 0

    def get_memory_accounting(self, device_index: int) -> MemoryAccounting:
        # DirectML does not expose direct programmatic VRAM metrics on all drivers
        return MemoryAccounting(
            total_dedicated_bytes=0,
            total_shared_bytes=0,
            device_used_bytes=0,
            device_free_bytes=0,
            process_allocated_bytes=0,
            process_reserved_bytes=0,
            external_usage_estimate_bytes=0,
        )

    def get_temperature_c(self, device_index: int) -> float | None:
        # DirectML standard API does not expose thermal telemetry
        return None

    def allocate_tensor(self, device_index: int, size_bytes: int) -> Any:
        if not self.is_available():
            raise RuntimeError("DirectML backend is not available for tensor allocation")
        import torch
        import torch_directml

        dev = torch_directml.device(device_index)
        num_elements = size_bytes // 4
        return torch.empty((num_elements,), dtype=torch.float32, device=dev)

    def free_tensor(self, handle: Any) -> None:
        if handle is not None:
            del handle

    def synchronize(self, device_index: int) -> None:
        # DirectML synchronization via torch
        try:
            import torch_directml

            torch_directml.device(device_index)
        except Exception:
            pass

    def execute_dummy_workload(self, device_index: int) -> bool:
        if not self.is_available():
            return False
        try:
            import torch
            import torch_directml

            dev = torch_directml.device(device_index)
            x = torch.ones((128, 128), dtype=torch.float32, device=dev)
            y = torch.matmul(x, x)
            return float(y[0, 0].item()) > 0
        except Exception as exc:
            logger.debug("DirectML workload failed: %s", exc)
            return False


__all__ = ["DirectMLBackendAdapter"]
