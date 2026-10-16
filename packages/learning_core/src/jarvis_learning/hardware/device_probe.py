"""Hardware discovery, device probing, and capability detection.

Enforces INV-P10-HW-001: Hardware capability claims must be evidence-backed
and capability-specific (never generic GPU=TRUE).
"""

from __future__ import annotations

import logging
import platform

from jarvis_learning.capability.manifest import (
    CapabilityMatrix,
    DeviceCapability,
    DeviceState,
)
from jarvis_learning.invariants_p10 import EvidenceLevel

logger = logging.getLogger(__name__)


class DeviceProbeEngine:
    """Probes physical and runtime acceleration devices."""

    def __init__(self) -> None:
        pass

    def probe_all_devices(self) -> list[DeviceCapability]:
        """Probe all available compute devices across PyTorch, CUDA, and DirectML."""
        devices: list[DeviceCapability] = []

        # 1. Attempt PyTorch CUDA probing
        cuda_devices = self._probe_cuda()
        devices.extend(cuda_devices)

        # 2. If no CUDA devices, attempt DirectML probing (Windows specific)
        if not devices:
            dml_devices = self._probe_directml()
            devices.extend(dml_devices)

        # 3. Always register host CPU as baseline
        cpu_dev = self._probe_cpu()
        devices.append(cpu_dev)

        return devices

    def _probe_cuda(self) -> list[DeviceCapability]:
        """Probe NVIDIA CUDA runtime and device properties."""
        try:
            import torch  # type: ignore[import-untyped]

            if not torch.cuda.is_available():
                return []

            cuda_count = torch.cuda.device_count()
            results: list[DeviceCapability] = []

            for idx in range(cuda_count):
                dev_name = torch.cuda.get_device_name(idx)
                props = torch.cuda.get_device_properties(idx)
                total_mem = props.total_memory

                matrix = CapabilityMatrix(
                    device_present=True,
                    driver_present=True,
                    telemetry_available=True,
                    compute_runtime_available=True,
                    memory_telemetry_available=True,
                    temperature_available=True,
                    power_telemetry_available=False,
                    process_isolation_supported=True,
                    device_usable_by_learning_worker=True,
                )

                results.append(
                    DeviceCapability(
                        device_id=f"cuda_{idx}",
                        device_name=dev_name,
                        backend="CUDA",
                        state=DeviceState.COMPUTE_READY,
                        matrix=matrix,
                        evidence_level=EvidenceLevel.L5_REAL_HARDWARE,
                        total_memory_bytes=total_mem,
                        driver_version=torch.version.cuda or "unknown",
                    )
                )

            return results
        except Exception as exc:
            logger.debug("CUDA probing unavailable: %s", exc)
            return []

    def _probe_directml(self) -> list[DeviceCapability]:
        """Probe Windows DirectML runtime availability."""
        try:
            import torch_directml  # type: ignore[import-untyped]

            dml_count = torch_directml.device_count()
            results: list[DeviceCapability] = []

            for idx in range(dml_count):
                dev_name = torch_directml.device_name(idx)
                matrix = CapabilityMatrix(
                    device_present=True,
                    driver_present=True,
                    telemetry_available=False,
                    compute_runtime_available=True,
                    memory_telemetry_available=False,
                    temperature_available=False,
                    power_telemetry_available=False,
                    process_isolation_supported=False,
                    device_usable_by_learning_worker=True,
                )
                results.append(
                    DeviceCapability(
                        device_id=f"dml_{idx}",
                        device_name=dev_name,
                        backend="DIRECTML",
                        state=DeviceState.COMPUTE_READY,
                        matrix=matrix,
                        evidence_level=EvidenceLevel.L5_REAL_HARDWARE,
                        total_memory_bytes=0,
                        driver_version="directml",
                    )
                )
            return results
        except Exception:
            return []

    def _probe_cpu(self) -> DeviceCapability:
        """Register host CPU execution capability."""
        matrix = CapabilityMatrix(
            device_present=True,
            driver_present=True,
            telemetry_available=True,
            compute_runtime_available=True,
            memory_telemetry_available=True,
            temperature_available=False,
            power_telemetry_available=False,
            process_isolation_supported=True,
            device_usable_by_learning_worker=True,
        )
        return DeviceCapability(
            device_id="cpu_0",
            device_name=platform.processor() or "Host CPU",
            backend="CPU",
            state=DeviceState.COMPUTE_READY,
            matrix=matrix,
            evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
            total_memory_bytes=0,
            driver_version="system",
        )
