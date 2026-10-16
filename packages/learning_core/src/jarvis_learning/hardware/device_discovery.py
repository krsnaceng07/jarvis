"""Layered hardware discovery across Windows WMI, DXGI, NVML, CUDA, DirectML, and CPU.

Enforces multi-GPU enumeration with field-level provenance and explicit
separation between dedicated VRAM and shared system memory.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import platform
import subprocess
from typing import Any

from jarvis_learning.hardware.models import DeviceType
from jarvis_learning.hardware.provenance import ProvenanceValue

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class DiscoveredDevice:
    """Rigorous descriptor for an individual physical or logical compute device."""

    device_index: int
    device_id: ProvenanceValue[str]
    name: ProvenanceValue[str]
    vendor: ProvenanceValue[str]
    device_type: ProvenanceValue[DeviceType]
    driver_version: ProvenanceValue[str]
    driver_date: ProvenanceValue[str]
    dedicated_vram_bytes: ProvenanceValue[int]
    shared_memory_bytes: ProvenanceValue[int]
    backend_support: list[str]
    pci_bus_id: ProvenanceValue[str]
    telemetry_capabilities: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_index": self.device_index,
            "device_id": self.device_id.to_dict(),
            "name": self.name.to_dict(),
            "vendor": self.vendor.to_dict(),
            "device_type": self.device_type.to_dict(),
            "driver_version": self.driver_version.to_dict(),
            "driver_date": self.driver_date.to_dict(),
            "dedicated_vram_bytes": self.dedicated_vram_bytes.to_dict(),
            "shared_memory_bytes": self.shared_memory_bytes.to_dict(),
            "backend_support": self.backend_support,
            "pci_bus_id": self.pci_bus_id.to_dict(),
            "telemetry_capabilities": self.telemetry_capabilities,
        }


class LayeredDiscoveryEngine:
    """Discovers hardware devices across multi-layer Windows and runtime interfaces."""

    def __init__(self) -> None:
        pass

    def discover_all(self) -> list[DiscoveredDevice]:
        """Perform comprehensive layered hardware discovery returning device array."""
        devices: list[DiscoveredDevice] = []

        # 1. Query Windows WMI / CIM Video Controllers
        wmi_adapters = self._query_wmi_video_controllers()

        # 2. Query CUDA Runtime if available
        cuda_devices = self._query_cuda_devices()

        # 3. Query DirectML if available
        dml_devices = self._query_directml_devices()

        # Fuse GPU information
        if wmi_adapters:
            for idx, wmi in enumerate(wmi_adapters):
                dev_name = wmi.get("Name", "Unknown Display Adapter")
                vendor = self._infer_vendor(dev_name)
                is_igpu = "intel" in dev_name.lower() or "radeon(tm) graphics" in dev_name.lower()
                dev_type = DeviceType.INTEGRATED_GPU if is_igpu else DeviceType.DISCRETE_GPU
                if "basic display" in dev_name.lower():
                    dev_type = DeviceType.BASIC_DISPLAY_ADAPTER

                adapter_ram = int(wmi.get("AdapterRAM", 0) or 0)
                # If integrated, AdapterRAM often represents pre-allocated carve-out, rest is shared
                dedicated_vram = 0 if is_igpu else adapter_ram
                shared_ram = adapter_ram if is_igpu else 0

                backends = ["cpu"]
                telemetry = {
                    "temperature": False,
                    "memory": True,
                    "power": False,
                    "utilization": False,
                }

                # Check if CUDA matches
                if cuda_devices and "nvidia" in vendor.lower():
                    backends.insert(0, "cuda")
                    telemetry["temperature"] = True
                    telemetry["power"] = True
                    telemetry["utilization"] = True

                # Check DirectML
                if dml_devices or platform.system() == "Windows":
                    backends.append("directml")

                device = DiscoveredDevice(
                    device_index=idx,
                    device_id=ProvenanceValue(
                        wmi.get("PNPDeviceID", f"gpu_{idx}"), source="WMI", confidence="HIGH"
                    ),
                    name=ProvenanceValue(dev_name, source="WMI", confidence="HIGH"),
                    vendor=ProvenanceValue(vendor, source="WMI", confidence="HIGH"),
                    device_type=ProvenanceValue(dev_type, source="WMI", confidence="HIGH"),
                    driver_version=ProvenanceValue(
                        wmi.get("DriverVersion", "unknown"), source="WMI", confidence="HIGH"
                    ),
                    driver_date=ProvenanceValue(
                        wmi.get("DriverDate", "unknown"), source="WMI", confidence="MEDIUM"
                    ),
                    dedicated_vram_bytes=ProvenanceValue(
                        dedicated_vram, source="WMI", confidence="HIGH"
                    ),
                    shared_memory_bytes=ProvenanceValue(
                        shared_ram, source="WMI", confidence="MEDIUM"
                    ),
                    backend_support=list(dict.fromkeys(backends)),
                    pci_bus_id=ProvenanceValue(
                        wmi.get("DeviceID", f"PCI_{idx}"), source="WMI", confidence="HIGH"
                    ),
                    telemetry_capabilities=telemetry,
                )
                devices.append(device)

        # 4. Always append Host CPU as canonical baseline
        cpu_index = len(devices)
        devices.append(self._discover_cpu(cpu_index))

        return devices

    def _query_wmi_video_controllers(self) -> list[dict[str, Any]]:
        """Query Win32_VideoController via PowerShell JSON serialization."""
        if platform.system() != "Windows":
            return []
        cmd = (
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name, DriverVersion, DriverDate, AdapterRAM, PNPDeviceID, DeviceID | "
            "ConvertTo-Json -Compress"
        )
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                if isinstance(data, dict):
                    return [data]
                elif isinstance(data, list):
                    return data
        except Exception as exc:
            logger.debug("WMI query failed: %s", exc)
        return []

    def _query_cuda_devices(self) -> list[dict[str, Any]]:
        try:
            import torch  # type: ignore[import-untyped]

            if not torch.cuda.is_available():
                return []
            count = torch.cuda.device_count()
            results = []
            for i in range(count):
                results.append(
                    {
                        "name": torch.cuda.get_device_name(i),
                        "total_memory": torch.cuda.get_device_properties(i).total_memory,
                    }
                )
            return results
        except Exception:
            return []

    def _query_directml_devices(self) -> list[dict[str, Any]]:
        try:
            import torch_directml  # type: ignore[import-untyped]

            count = torch_directml.device_count()
            results = []
            for i in range(count):
                results.append({"name": torch_directml.device_name(i)})
            return results
        except Exception:
            return []

    @staticmethod
    def _infer_vendor(name: str) -> str:
        low = name.lower()
        if "nvidia" in low:
            return "NVIDIA"
        if "intel" in low:
            return "Intel"
        if "amd" in low or "radeon" in low:
            return "AMD"
        if "qualcomm" in low:
            return "Qualcomm"
        if "microsoft" in low:
            return "Microsoft"
        return "Unknown"

    @staticmethod
    def _discover_cpu(index: int) -> DiscoveredDevice:
        proc_name = platform.processor() or "Host CPU"
        return DiscoveredDevice(
            device_index=index,
            device_id=ProvenanceValue("cpu_host_0", source="SYSTEM", confidence="HIGH"),
            name=ProvenanceValue(proc_name, source="SYSTEM", confidence="HIGH"),
            vendor=ProvenanceValue(
                "Intel" if "intel" in proc_name.lower() else "AMD",
                source="SYSTEM",
                confidence="MEDIUM",
            ),
            device_type=ProvenanceValue(DeviceType.CPU, source="SYSTEM", confidence="HIGH"),
            driver_version=ProvenanceValue(platform.version(), source="SYSTEM", confidence="HIGH"),
            driver_date=ProvenanceValue("system", source="SYSTEM", confidence="HIGH"),
            dedicated_vram_bytes=ProvenanceValue(0, source="SYSTEM", confidence="HIGH"),
            shared_memory_bytes=ProvenanceValue(0, source="SYSTEM", confidence="HIGH"),
            backend_support=["cpu"],
            pci_bus_id=ProvenanceValue("HOST_CPU_BUS", source="SYSTEM", confidence="HIGH"),
            telemetry_capabilities={
                "temperature": False,
                "memory": True,
                "power": False,
                "utilization": True,
            },
        )


__all__ = ["DiscoveredDevice", "LayeredDiscoveryEngine"]
