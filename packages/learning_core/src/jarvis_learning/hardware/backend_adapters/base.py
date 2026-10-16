"""Base contract for accelerator backend execution adapters."""

from __future__ import annotations

import abc
from typing import Any

from jarvis_learning.hardware.models import MemoryAccounting


class BaseBackendAdapter(abc.ABC):
    """Abstract interface across CUDA, DirectML, and CPU execution engines."""

    @property
    @abc.abstractmethod
    def backend_name(self) -> str:
        """Normalized backend name (e.g. CUDA, DIRECTML, CPU)."""

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if runtime driver and library are functional."""

    @abc.abstractmethod
    def get_device_count(self) -> int:
        """Number of operational acceleration devices."""

    @abc.abstractmethod
    def get_memory_accounting(self, device_index: int) -> MemoryAccounting:
        """Query authoritative memory usage, capacity, and headroom."""

    @abc.abstractmethod
    def get_temperature_c(self, device_index: int) -> float | None:
        """Query physical temperature sensor reading in Celsius if available."""

    @abc.abstractmethod
    def allocate_tensor(self, device_index: int, size_bytes: int) -> Any:
        """Allocate real physical memory or compute tensor on device."""

    @abc.abstractmethod
    def free_tensor(self, handle: Any) -> None:
        """Release allocated physical memory tensor."""

    @abc.abstractmethod
    def synchronize(self, device_index: int) -> None:
        """Synchronize execution stream ensuring compute/allocations completed."""

    @abc.abstractmethod
    def execute_dummy_workload(self, device_index: int) -> bool:
        """Execute a lightweight compute operation proving execution capability."""


__all__ = ["BaseBackendAdapter"]
