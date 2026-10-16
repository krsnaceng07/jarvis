"""jarvis_learning.training.reproducibility — reproducibility fingerprints and profile-based tolerances.

Replaces unrealistic universal 0.0 delta claims with profile-based tolerance
specifications (CPU deterministic, FP32, FP16, BF16) and cryptographic run fingerprints.
"""

from __future__ import annotations

import enum
import hashlib
import json
import math
import platform
import sys
from dataclasses import dataclass
from typing import Any


class PrecisionMode(enum.StrEnum):
    """Execution precision and determinism profile."""

    CPU_DETERMINISTIC = "CPU_DETERMINISTIC"
    GPU_FP32 = "GPU_FP32"
    GPU_FP16 = "GPU_FP16"
    GPU_BF16 = "GPU_BF16"


@dataclass(frozen=True, slots=True)
class ToleranceProfile:
    """Declared numerical tolerance boundaries for a precision mode."""

    precision_mode: PrecisionMode
    max_absolute_weight_delta: float
    max_metric_delta: float
    deterministic_parity_required: bool

    @classmethod
    def get_profile(cls, mode: PrecisionMode) -> ToleranceProfile:
        """Fetch canonical tolerance thresholds for a precision mode."""
        match mode:
            case PrecisionMode.CPU_DETERMINISTIC:
                return cls(
                    precision_mode=mode,
                    max_absolute_weight_delta=1e-7,
                    max_metric_delta=1e-6,
                    deterministic_parity_required=True,
                )
            case PrecisionMode.GPU_FP32:
                return cls(
                    precision_mode=mode,
                    max_absolute_weight_delta=1e-6,
                    max_metric_delta=1e-5,
                    deterministic_parity_required=False,
                )
            case PrecisionMode.GPU_FP16:
                return cls(
                    precision_mode=mode,
                    max_absolute_weight_delta=5e-3,
                    max_metric_delta=1e-3,
                    deterministic_parity_required=False,
                )
            case PrecisionMode.GPU_BF16:
                return cls(
                    precision_mode=mode,
                    max_absolute_weight_delta=1e-2,
                    max_metric_delta=5e-3,
                    deterministic_parity_required=False,
                )


@dataclass(frozen=True, slots=True)
class ReproducibilityFingerprint:
    """Cryptographic and environment identity of a training execution."""

    seed: int
    dataset_manifest_hash: str
    config_hash: str
    commit_hash: str
    python_version: str
    hardware_fingerprint: str
    precision_mode: PrecisionMode

    framework_version: str = "torch-none"
    cuda_version: str = "none"
    driver_version: str = "none"
    tokenizer_hash: str = "none"
    model_base_hash: str = "none"
    determinism_mode: str = "strict"
    batching_policy_hash: str = "none"
    loss_strategy_hash: str = "none"

    @classmethod
    def create(
        cls,
        seed: int,
        dataset_manifest_hash: str,
        config_hash: str,
        commit_hash: str = "HEAD",
        hardware_fingerprint: str = "",
        precision_mode: PrecisionMode = PrecisionMode.CPU_DETERMINISTIC,
        framework_version: str = "torch-none",
        cuda_version: str = "none",
        driver_version: str = "none",
        tokenizer_hash: str = "none",
        model_base_hash: str = "none",
        determinism_mode: str = "strict",
        batching_policy_hash: str = "none",
        loss_strategy_hash: str = "none",
    ) -> ReproducibilityFingerprint:
        """Create a fingerprint capturing current environment facts."""
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        hw = hardware_fingerprint or f"{platform.system()}-{platform.machine()}"
        return cls(
            seed=seed,
            dataset_manifest_hash=dataset_manifest_hash,
            config_hash=config_hash,
            commit_hash=commit_hash,
            python_version=py_ver,
            hardware_fingerprint=hw,
            precision_mode=precision_mode,
            framework_version=framework_version,
            cuda_version=cuda_version,
            driver_version=driver_version,
            tokenizer_hash=tokenizer_hash,
            model_base_hash=model_base_hash,
            determinism_mode=determinism_mode,
            batching_policy_hash=batching_policy_hash,
            loss_strategy_hash=loss_strategy_hash,
        )

    def compute_hash(self) -> str:
        """Compute deterministic SHA-256 digest of the run fingerprint."""
        payload = {
            "batching_policy_hash": self.batching_policy_hash,
            "commit_hash": self.commit_hash,
            "config_hash": self.config_hash,
            "cuda_version": self.cuda_version,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "determinism_mode": self.determinism_mode,
            "driver_version": self.driver_version,
            "framework_version": self.framework_version,
            "hardware_fingerprint": self.hardware_fingerprint,
            "loss_strategy_hash": self.loss_strategy_hash,
            "model_base_hash": self.model_base_hash,
            "precision_mode": self.precision_mode.value,
            "python_version": self.python_version,
            "seed": self.seed,
            "tokenizer_hash": self.tokenizer_hash,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "seed": self.seed,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "config_hash": self.config_hash,
            "commit_hash": self.commit_hash,
            "python_version": self.python_version,
            "hardware_fingerprint": self.hardware_fingerprint,
            "precision_mode": self.precision_mode.value,
            "framework_version": self.framework_version,
            "cuda_version": self.cuda_version,
            "driver_version": self.driver_version,
            "tokenizer_hash": self.tokenizer_hash,
            "model_base_hash": self.model_base_hash,
            "determinism_mode": self.determinism_mode,
            "batching_policy_hash": self.batching_policy_hash,
            "loss_strategy_hash": self.loss_strategy_hash,
            "fingerprint_hash": self.compute_hash(),
        }


def check_numerical_equivalence(
    val_a: float,
    val_b: float,
    mode: PrecisionMode = PrecisionMode.CPU_DETERMINISTIC,
) -> bool:
    """Verify whether two values match within the declared tolerance profile."""
    profile = ToleranceProfile.get_profile(mode)
    delta = abs(val_a - val_b)
    if math.isnan(val_a) or math.isnan(val_b):
        return False
    return delta <= profile.max_absolute_weight_delta


@dataclass(frozen=True, slots=True)
class RunIdentity:
    """Unique runtime instance identifier protecting against duplicate executions (INV-REP-001)."""

    run_id: str
    created_at: str
    attempt_number: int = 1
    supervisor_instance_id: str = ""
    run_hash: str = ""

    @classmethod
    def create(
        cls,
        attempt_number: int = 1,
        supervisor_instance_id: str = "",
    ) -> RunIdentity:
        import time
        import uuid

        run_id = f"run_{uuid.uuid4().hex}"
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        h = hashlib.sha256(
            f"{run_id}:{attempt_number}:{supervisor_instance_id}:{created_at}".encode("utf-8")
        ).hexdigest()
        return cls(
            run_id=run_id,
            created_at=created_at,
            attempt_number=attempt_number,
            supervisor_instance_id=supervisor_instance_id,
            run_hash=h,
        )


@dataclass(frozen=True, slots=True)
class ResumeCompatibilityFingerprint:
    """Subset of execution fingerprint strictly required for safe resume compatibility (INV-RES-001)."""

    dataset_manifest_hash: str
    config_hash: str
    model_base_hash: str
    tokenizer_hash: str
    batching_policy_hash: str
    loss_strategy_hash: str
    seed: int
    precision_mode: PrecisionMode
    python_major_minor: str
    framework_major_minor: str
    device_type: str

    def can_resume(self, target: ResumeCompatibilityFingerprint) -> tuple[bool, list[str]]:
        """Verify resume compatibility against target fingerprint."""
        mismatches: list[str] = []
        if self.dataset_manifest_hash != target.dataset_manifest_hash:
            mismatches.append(
                f"dataset_manifest_hash mismatch: '{self.dataset_manifest_hash}' vs '{target.dataset_manifest_hash}'"
            )
        if self.config_hash != target.config_hash:
            mismatches.append(
                f"config_hash mismatch: '{self.config_hash}' vs '{target.config_hash}'"
            )
        if self.model_base_hash != target.model_base_hash:
            mismatches.append(
                f"model_base_hash mismatch: '{self.model_base_hash}' vs '{target.model_base_hash}'"
            )
        if self.tokenizer_hash != target.tokenizer_hash:
            mismatches.append(
                f"tokenizer_hash mismatch: '{self.tokenizer_hash}' vs '{target.tokenizer_hash}'"
            )
        if self.batching_policy_hash != target.batching_policy_hash:
            mismatches.append(
                f"batching_policy_hash mismatch: '{self.batching_policy_hash}' vs '{target.batching_policy_hash}'"
            )
        if self.loss_strategy_hash != target.loss_strategy_hash:
            mismatches.append(
                f"loss_strategy_hash mismatch: '{self.loss_strategy_hash}' vs '{target.loss_strategy_hash}'"
            )
        if self.seed != target.seed:
            mismatches.append(f"seed mismatch: {self.seed} vs {target.seed}")
        if self.precision_mode != target.precision_mode:
            mismatches.append(
                f"precision_mode mismatch: {self.precision_mode} vs {target.precision_mode}"
            )
        if self.python_major_minor != target.python_major_minor:
            mismatches.append(
                f"python_major_minor mismatch: '{self.python_major_minor}' vs '{target.python_major_minor}'"
            )
        if self.framework_major_minor != target.framework_major_minor:
            mismatches.append(
                f"framework_major_minor mismatch: '{self.framework_major_minor}' vs '{target.framework_major_minor}'"
            )
        if self.device_type != target.device_type:
            mismatches.append(
                f"device_type mismatch: '{self.device_type}' vs '{target.device_type}'"
            )

        return len(mismatches) == 0, mismatches


@dataclass(frozen=True, slots=True)
class ExecutionFingerprint:
    """Comprehensive 22+ attribute environmental and hardware state record for debugging and audits."""

    python_version: str
    python_implementation: str
    platform_system: str
    platform_release: str
    platform_machine: str
    cpu_count: int
    torch_version: str
    cuda_available: bool
    cuda_version: str
    cudnn_version: str
    gpu_device_name: str
    gpu_driver_version: str
    gpu_memory_total_mb: float
    seed: int
    dataset_manifest_hash: str
    config_hash: str
    commit_hash: str
    tokenizer_hash: str
    model_base_hash: str
    determinism_mode: str
    batching_policy_hash: str
    loss_strategy_hash: str
    precision_mode: PrecisionMode

    @classmethod
    def capture_current(
        cls,
        seed: int,
        dataset_manifest_hash: str,
        config_hash: str,
        commit_hash: str = "HEAD",
        tokenizer_hash: str = "none",
        model_base_hash: str = "none",
        determinism_mode: str = "strict",
        batching_policy_hash: str = "none",
        loss_strategy_hash: str = "none",
        precision_mode: PrecisionMode = PrecisionMode.CPU_DETERMINISTIC,
    ) -> ExecutionFingerprint:
        import os

        torch_ver = "none"
        cuda_avail = False
        cuda_ver = "none"
        cudnn_ver = "none"
        gpu_name = "none"
        gpu_driver = "none"
        gpu_mem = 0.0

        try:
            import torch

            torch_ver = torch.__version__
            cuda_avail = torch.cuda.is_available()
            if cuda_avail:
                cuda_ver = torch.version.cuda or "none"
                cudnn_ver = (
                    str(torch.backends.cudnn.version())
                    if torch.backends.cudnn.is_available()
                    else "none"
                )
                gpu_name = (
                    torch.cuda.get_device_name(0) if torch.cuda.device_count() > 0 else "none"
                )
                if torch.cuda.device_count() > 0:
                    gpu_mem = float(torch.cuda.get_device_properties(0).total_memory) / (
                        1024 * 1024
                    )
        except Exception:
            pass

        return cls(
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            python_implementation=platform.python_implementation(),
            platform_system=platform.system(),
            platform_release=platform.release(),
            platform_machine=platform.machine(),
            cpu_count=os.cpu_count() or 1,
            torch_version=torch_ver,
            cuda_available=cuda_avail,
            cuda_version=cuda_ver,
            cudnn_version=cudnn_ver,
            gpu_device_name=gpu_name,
            gpu_driver_version=gpu_driver,
            gpu_memory_total_mb=gpu_mem,
            seed=seed,
            dataset_manifest_hash=dataset_manifest_hash,
            config_hash=config_hash,
            commit_hash=commit_hash,
            tokenizer_hash=tokenizer_hash,
            model_base_hash=model_base_hash,
            determinism_mode=determinism_mode,
            batching_policy_hash=batching_policy_hash,
            loss_strategy_hash=loss_strategy_hash,
            precision_mode=precision_mode,
        )

    def to_resume_fingerprint(self, device_type: str = "cpu") -> ResumeCompatibilityFingerprint:
        py_major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
        fw_major_minor = "none"
        if self.torch_version != "none":
            fw_major_minor = ".".join(self.torch_version.split(".")[:2])

        return ResumeCompatibilityFingerprint(
            dataset_manifest_hash=self.dataset_manifest_hash,
            config_hash=self.config_hash,
            model_base_hash=self.model_base_hash,
            tokenizer_hash=self.tokenizer_hash,
            batching_policy_hash=self.batching_policy_hash,
            loss_strategy_hash=self.loss_strategy_hash,
            seed=self.seed,
            precision_mode=self.precision_mode,
            python_major_minor=py_major_minor,
            framework_major_minor=fw_major_minor,
            device_type=device_type,
        )
