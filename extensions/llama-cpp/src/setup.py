"""Setup readiness and hardware evaluation routines for llama.cpp."""

from __future__ import annotations

from dataclasses import dataclass, field

from .backends import detect_execution_backend
from .config import LlamaCppConfig
from .models import HardwareMetrics, recommend_model_for_hardware


@dataclass(slots=True)
class LlamaCppSetupCheck:
    id: str
    ok: bool
    message: str


@dataclass(slots=True)
class LlamaCppSetupStatus:
    ok: bool
    checks: list[LlamaCppSetupCheck] = field(default_factory=list)
    recommended_model: str | None = None
    execution_backend: str = "CPU"


def get_llama_cpp_setup_status(
    config: LlamaCppConfig,
    *,
    hardware_metrics: HardwareMetrics | None = None,
) -> LlamaCppSetupStatus:
    """Evaluate llama.cpp setup readiness, hardware fit, and backend discovery."""
    checks: list[LlamaCppSetupCheck] = []

    # 1. Plugin enablement
    checks.append(
        LlamaCppSetupCheck(
            id="llama-cpp-enabled",
            ok=config.enabled,
            message=(
                "llama.cpp provider is enabled"
                if config.enabled
                else "llama.cpp provider is disabled"
            ),
        )
    )

    # 2. Execution backend detection
    backend = detect_execution_backend()
    checks.append(
        LlamaCppSetupCheck(
            id="execution-backend",
            ok=True,
            message=f"Execution backend: {backend.backend_name} ({backend.notes})",
        )
    )

    # 3. Hardware recommendation check (if managed mode)
    metrics = hardware_metrics or HardwareMetrics(
        ram_gib=16.0,
        free_ram_gib=12.0,
        has_gpu=backend.is_accelerated,
        gpu_type="cuda"
        if "CUDA" in backend.backend_name
        else ("metal" if "Metal" in backend.backend_name else "cpu"),
        vram_gib=8.0 if backend.is_accelerated else 0.0,
        free_disk_gb=40.0,
    )
    rec = recommend_model_for_hardware(metrics)
    if config.is_managed:
        if rec:
            checks.append(
                LlamaCppSetupCheck(
                    id="hardware-recommendation",
                    ok=True,
                    message=f"Recommended model for host hardware: {rec.name} ({rec.download_size_gb} GB download)",
                )
            )
        else:
            checks.append(
                LlamaCppSetupCheck(
                    id="hardware-recommendation",
                    ok=False,
                    message="No recommended model fits current host memory/disk constraints. Free RAM/disk or choose an existing llama-server.",
                )
            )
    else:
        checks.append(
            LlamaCppSetupCheck(
                id="existing-server-mode",
                ok=bool(config.base_url),
                message=f"Configured to connect to existing llama-server at {config.base_url}",
            )
        )

    all_ok = all(c.ok for c in checks)
    return LlamaCppSetupStatus(
        ok=all_ok,
        checks=checks,
        recommended_model=rec.id if rec else None,
        execution_backend=backend.backend_name,
    )
