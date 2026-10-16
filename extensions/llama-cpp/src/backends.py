"""Execution backend detection and hardware discovery for llama.cpp."""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass


@dataclass(slots=True)
class BackendInfo:
    backend_name: str  # "Metal with unified memory", "CUDA 12.4", "CPU"
    is_accelerated: bool
    platform_os: str
    architecture: str
    driver_version: str | None = None
    compute_capability: float | None = None
    notes: str = ""


def detect_execution_backend(
    *,
    os_override: str | None = None,
    arch_override: str | None = None,
    nvidia_driver: str | None = None,
    cuda_compute_cap: float | None = None,
) -> BackendInfo:
    """Detect the managed execution backend for the Gateway host.

    Verified rules:
    - macOS Apple Silicon: Metal with unified memory
    - macOS Intel: CPU
    - Linux x64/arm64: CPU (requires glibc 2.34+ on x64, 2.38+ on arm64)
    - Windows x64 with NVIDIA GPU (driver >= 551.78, compute capability >= 5.0): CUDA 12.4
    - Windows x64 without CUDA / Windows arm64: CPU
    """
    sys_os = os_override or sys.platform
    arch = (arch_override or platform.machine()).lower()

    # 1. macOS detection
    if sys_os == "darwin" or sys_os.startswith("mac"):
        if arch in ("arm64", "aarch64"):
            return BackendInfo(
                backend_name="Metal with unified memory",
                is_accelerated=True,
                platform_os="macOS",
                architecture="arm64",
                notes="Accelerated via Apple Metal and unified memory architecture",
            )
        return BackendInfo(
            backend_name="CPU",
            is_accelerated=False,
            platform_os="macOS",
            architecture=arch,
            notes="macOS on Intel CPU execution",
        )

    # 2. Windows detection
    if sys_os in ("win32", "windows") or sys.platform == "win32":
        if arch in ("amd64", "x86_64", "x64"):
            # Check NVIDIA CUDA support
            driver = nvidia_driver or os.environ.get("NVIDIA_DRIVER_VERSION")
            compute_cap = cuda_compute_cap
            if driver:
                try:
                    driver_ver = float(driver.split()[0].strip())
                    if driver_ver >= 551.78 and (compute_cap is None or compute_cap >= 5.0):
                        return BackendInfo(
                            backend_name="CUDA 12.4",
                            is_accelerated=True,
                            platform_os="Windows",
                            architecture="x64",
                            driver_version=driver,
                            compute_capability=compute_cap or 7.5,
                            notes="NVIDIA CUDA 12.4 acceleration active (driver >= 551.78, CC >= 5.0)",
                        )
                except ValueError:
                    pass

            return BackendInfo(
                backend_name="CPU",
                is_accelerated=False,
                platform_os="Windows",
                architecture="x64",
                notes="Windows x64 CPU execution (requires MSVC 2015-2022 Redistributable)",
            )

        return BackendInfo(
            backend_name="CPU",
            is_accelerated=False,
            platform_os="Windows",
            architecture=arch,
            notes=f"Windows {arch} CPU execution",
        )

    # 3. Linux / Unix detection
    return BackendInfo(
        backend_name="CPU",
        is_accelerated=False,
        platform_os="Linux",
        architecture=arch,
        notes="Linux CPU execution (requires glibc 2.34 on x64 or 2.38 on arm64)",
    )
