"""jarvis_learning.training.gpu_governor — GPU device discovery, VRAM tracking, and OOM handling.

Enforces device visibility, monitors VRAM allocations, handles CUDA OOM with
bounded batch-size reduction vs fatal classification, and guarantees clean context release.
"""

from __future__ import annotations

import enum
import gc
import logging
import os
from dataclasses import dataclass
from typing import Any

from .errors import GpuOOMError

logger = logging.getLogger(__name__)


class GpuFailureClass(enum.StrEnum):
    """Granular classification of GPU runtime and memory failures."""

    GPU_OOM_BATCH = "GPU_OOM_BATCH"
    GPU_OOM_MODEL_STATE = "GPU_OOM_MODEL_STATE"
    GPU_OOM_FRAGMENTATION = "GPU_OOM_FRAGMENTATION"
    CUDA_DRIVER_FAILURE = "CUDA_DRIVER_FAILURE"
    CUDA_DEVICE_LOST = "CUDA_DEVICE_LOST"
    CUDA_UNAVAILABLE = "CUDA_UNAVAILABLE"
    GPU_MEMORY_BUDGET_EXCEEDED = "GPU_MEMORY_BUDGET_EXCEEDED"
    GPU_RUNTIME_ERROR = "GPU_RUNTIME_ERROR"


@dataclass(frozen=True, slots=True)
class GpuOomOutcome:
    """Classified resolution for a GPU Out-Of-Memory or runtime exception."""

    is_recoverable: bool
    suggested_batch_size: int
    action: str  # "REDUCE_BATCH_SIZE", "ABORT_JOB", "TERMINATE_WORKER"
    reason: str = ""
    failure_class: GpuFailureClass = GpuFailureClass.GPU_OOM_BATCH
    requires_process_restart: bool = False


@dataclass(frozen=True, slots=True)
class GpuGovernor:
    """Governs GPU device assignment, VRAM tracking, failure classification, and clean recycling."""

    allowed_device_id: int = 0
    max_vram_mb: int = 4096
    enable_gpu: bool = False
    max_oom_retries: int = 3
    allow_cpu_fallback: bool = True

    def configure_environment(self, env: dict[str, str] | None = None) -> dict[str, str]:
        """Configure CUDA_VISIBLE_DEVICES to restrict child process to designated GPU."""
        target_env = dict(os.environ if env is None else env)
        if self.enable_gpu:
            target_env["CUDA_VISIBLE_DEVICES"] = str(self.allowed_device_id)
        else:
            target_env["CUDA_VISIBLE_DEVICES"] = ""  # Disable CUDA visibility
        return target_env

    @staticmethod
    def is_cuda_available() -> bool:
        """Check if CUDA runtime and devices are available."""
        try:
            import torch

            return bool(torch.cuda.is_available() and torch.cuda.device_count() > 0)
        except Exception:
            return False

    def resolve_compute_device(self, raise_if_unavailable: bool = False) -> str:
        """Resolve device string respecting availability and GPU policy."""
        if self.enable_gpu:
            if self.is_cuda_available():
                return f"cuda:{self.allowed_device_id}"
            if not self.allow_cpu_fallback or raise_if_unavailable:
                raise GpuOOMError("GPU compute required by policy but CUDA is unavailable")
        return "cpu"

    def get_vram_usage_mb(self) -> tuple[float, float]:
        """Query currently allocated and reserved GPU VRAM in megabytes."""
        try:
            import torch

            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / (1024 * 1024)
                reserved = torch.cuda.memory_reserved() / (1024 * 1024)
                return round(allocated, 2), round(reserved, 2)
        except Exception:
            pass
        return 0.0, 0.0

    def classify_gpu_failure(
        self,
        exc: BaseException,
        current_batch_size: int,
        phase: str = "forward",
        min_batch_size: int = 1,
        retry_count: int = 0,
    ) -> GpuOomOutcome:
        """Classify GPU runtime or OOM error into 8 granular failure classes with clean worker recycling."""
        err_msg = str(exc).lower()

        # 1. Device lost / driver failure / GPU disappearing
        if any(
            term in err_msg
            for term in (
                "device-side assert",
                "device lost",
                "hardware error",
                "disappeared",
                "driver reset",
            )
        ):
            logger.critical("CUDA device lost or unrecoverable hardware fault: %s", exc)
            return GpuOomOutcome(
                is_recoverable=False,
                suggested_batch_size=current_batch_size,
                action="TERMINATE_WORKER",
                reason="CUDA_DEVICE_LOST",
                failure_class=GpuFailureClass.CUDA_DEVICE_LOST,
                requires_process_restart=True,
            )

        # 2. Optimizer step OOM
        if phase == "optimizer" and ("out of memory" in err_msg or isinstance(exc, GpuOOMError)):
            logger.error("CUDA OOM during optimizer step; model states/gradients exceed VRAM")
            return GpuOomOutcome(
                is_recoverable=False,
                suggested_batch_size=current_batch_size,
                action="ABORT_JOB",
                reason="GPU_OOM_MODEL_STATE: optimizer memory cannot be reduced via batch size",
                failure_class=GpuFailureClass.GPU_OOM_MODEL_STATE,
                requires_process_restart=True,
            )

        # 3. Standard OOM (forward / backward pass)
        is_cuda_oom = "out of memory" in err_msg or isinstance(exc, GpuOOMError)
        if is_cuda_oom:
            if retry_count >= self.max_oom_retries:
                logger.error(
                    "CUDA OOM retry count (%d) reached maximum (%d)",
                    retry_count,
                    self.max_oom_retries,
                )
                return GpuOomOutcome(
                    is_recoverable=False,
                    suggested_batch_size=current_batch_size,
                    action="ABORT_JOB",
                    reason="GPU_OOM_MAX_RETRIES_EXCEEDED",
                    failure_class=GpuFailureClass.GPU_OOM_BATCH,
                    requires_process_restart=True,
                )

            if current_batch_size > min_batch_size:
                halved = max(min_batch_size, current_batch_size // 2)
                return GpuOomOutcome(
                    is_recoverable=True,
                    suggested_batch_size=halved,
                    action="REDUCE_BATCH_SIZE",
                    reason="BATCH_SIZE_HALVED",
                    failure_class=GpuFailureClass.GPU_OOM_BATCH,
                    requires_process_restart=True,
                )

            return GpuOomOutcome(
                is_recoverable=False,
                suggested_batch_size=current_batch_size,
                action="ABORT_JOB",
                reason="GPU_OOM_MIN_BATCH_REACHED",
                failure_class=GpuFailureClass.GPU_OOM_BATCH,
                requires_process_restart=True,
            )

        return GpuOomOutcome(
            is_recoverable=False,
            suggested_batch_size=current_batch_size,
            action="ABORT_JOB",
            reason=f"GPU_RUNTIME_ERROR: {exc}",
            failure_class=GpuFailureClass.GPU_RUNTIME_ERROR,
            requires_process_restart=True,
        )

    def classify_oom(
        self,
        exc: BaseException,
        current_batch_size: int,
        min_batch_size: int = 1,
        retry_count: int = 0,
    ) -> GpuOomOutcome:
        """Backward-compatible classification delegating to classify_gpu_failure."""
        return self.classify_gpu_failure(
            exc=exc,
            current_batch_size=current_batch_size,
            phase="forward",
            min_batch_size=min_batch_size,
            retry_count=retry_count,
        )

    @staticmethod
    def cleanup_cuda_context() -> None:
        """Release cached GPU memory and trigger garbage collection."""
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
                logger.debug("CUDA memory cache cleared")
        except Exception:
            pass
        gc.collect()

    def to_dict(self) -> dict[str, Any]:
        """Diagnostic state serialization."""
        alloc, res = self.get_vram_usage_mb()
        return {
            "enable_gpu": self.enable_gpu,
            "allowed_device_id": self.allowed_device_id,
            "max_vram_mb": self.max_vram_mb,
            "allocated_vram_mb": alloc,
            "reserved_vram_mb": res,
            "resolved_device": self.resolve_compute_device(),
        }


def classify_gpu_failure(exc: BaseException, phase: str = "forward") -> GpuFailureClass:
    """Classify an exception into one of the 8 GpuFailureClass categories."""
    msg = str(exc).lower()
    if (
        "device-side assert" in msg
        or "device lost" in msg
        or "illegal memory access" in msg
        or "hardware error" in msg
    ):
        return GpuFailureClass.CUDA_DEVICE_LOST
    if "cuda driver" in msg or "driver version" in msg:
        return GpuFailureClass.CUDA_DRIVER_FAILURE
    if "cuda unavailable" in msg or "no cuda" in msg or "not available" in msg:
        return GpuFailureClass.CUDA_UNAVAILABLE
    if phase == "optimizer" and ("out of memory" in msg or "oom" in msg):
        return GpuFailureClass.GPU_OOM_MODEL_STATE
    if "fragmentation" in msg or "allocator" in msg:
        return GpuFailureClass.GPU_OOM_FRAGMENTATION
    if "out of memory" in msg or "oom" in msg:
        return GpuFailureClass.GPU_OOM_BATCH
    if "budget exceeded" in msg:
        return GpuFailureClass.GPU_MEMORY_BUDGET_EXCEEDED
    return GpuFailureClass.GPU_RUNTIME_ERROR
