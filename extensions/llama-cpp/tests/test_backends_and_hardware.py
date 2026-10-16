"""Unit tests for execution backend discovery across platforms."""

from __future__ import annotations

from extensions.llama_cpp.src.backends import detect_execution_backend


def test_macos_backend_detection() -> None:
    # macOS Apple Silicon
    be_m1 = detect_execution_backend(os_override="darwin", arch_override="arm64")
    assert be_m1.backend_name == "Metal with unified memory"
    assert be_m1.is_accelerated is True

    # macOS Intel
    be_intel = detect_execution_backend(os_override="darwin", arch_override="x86_64")
    assert be_intel.backend_name == "CPU"
    assert be_intel.is_accelerated is False


def test_windows_backend_detection() -> None:
    # Windows with valid NVIDIA CUDA driver (>= 551.78) and CC (>= 5.0)
    be_cuda = detect_execution_backend(
        os_override="win32",
        arch_override="x64",
        nvidia_driver="551.86",
        cuda_compute_cap=7.5,
    )
    assert be_cuda.backend_name == "CUDA 12.4"
    assert be_cuda.is_accelerated is True

    # Windows with older unsupported driver (< 551.78)
    be_old_driver = detect_execution_backend(
        os_override="win32",
        arch_override="x64",
        nvidia_driver="535.10",
    )
    assert be_old_driver.backend_name == "CPU"
    assert be_old_driver.is_accelerated is False

    # Windows without NVIDIA GPU
    be_win_cpu = detect_execution_backend(
        os_override="win32",
        arch_override="x64",
        nvidia_driver=None,
    )
    assert be_win_cpu.backend_name == "CPU"


def test_linux_backend_detection() -> None:
    be_linux = detect_execution_backend(os_override="linux", arch_override="x86_64")
    assert be_linux.backend_name == "CPU"
    assert be_linux.is_accelerated is False
