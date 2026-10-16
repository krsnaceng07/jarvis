"""jarvis_learning.training.cpu_governor — multi-library CPU thread control.

Applies strict thread limits across OpenMP, MKL, OpenBLAS, NumExpr, VecLib,
HuggingFace Tokenizers, and PyTorch before ML packages initialize.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Mapping

logger = logging.getLogger(__name__)

CPU_THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


@dataclass(frozen=True, slots=True)
class CpuGovernor:
    """Configures environment and runtime thread bounds."""

    max_threads: int = 3

    def build_subprocess_env(self, base_env: Mapping[str, str] | None = None) -> dict[str, str]:
        """Build an environment dictionary pre-populated with CPU thread caps."""
        env = dict(os.environ if base_env is None else base_env)
        threads_str = str(max(1, self.max_threads))
        for var in CPU_THREAD_ENV_VARS:
            env[var] = threads_str
        env["TOKENIZERS_PARALLELISM"] = "false"
        return env

    def apply_current_process_env(self) -> None:
        """Set thread limit environment variables in the current process."""
        threads_str = str(max(1, self.max_threads))
        for var in CPU_THREAD_ENV_VARS:
            os.environ[var] = threads_str
        os.environ["TOKENIZERS_PARALLELISM"] = "false"

    def apply_runtime_thread_limits(self) -> None:
        """Set thread limits on imported PyTorch runtime if available."""
        self.apply_current_process_env()
        try:
            import torch

            torch.set_num_threads(max(1, self.max_threads))
            interop_threads = max(1, min(2, self.max_threads))
            torch.set_num_interop_threads(interop_threads)
            logger.debug(
                "Applied torch thread limits: intra=%d, interop=%d",
                self.max_threads,
                interop_threads,
            )
        except ImportError:
            pass
        except RuntimeError as exc:
            # torch raises RuntimeError if already initialized or threads cannot be set
            logger.debug("Could not set torch thread limits: %s", exc)
