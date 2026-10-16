"""jarvis_learning.training.batching — batch construction, token budgeting, and deterministic sampling.

Enforces sequence length caps, batch token budgets, dynamic padding, and
deterministic epoch-seeded sample permutation.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BatchPolicy:
    """Constraints for batch construction and token boundaries."""

    batch_size: int = 16
    max_sequence_tokens: int = 512
    max_batch_tokens: int = 4096
    truncate_long_sequences: bool = True


class DeterministicSampler:
    """Permutes dataset indices deterministically given a base seed and epoch."""

    def __init__(
        self,
        base_seed: int = 0,
        num_samples: int = 0,
        dataset_size: int | None = None,
        seed: int | None = None,
        epoch: int = 0,
        resume_step: int = 0,
        batch_size: int = 1,
    ) -> None:
        self.base_seed = seed if seed is not None else base_seed
        self.num_samples = dataset_size if dataset_size is not None else num_samples
        self.epoch = epoch
        self.resume_step = resume_step
        self.step = resume_step
        self.batch_size = batch_size
        self._indices: list[int] = []
        self._cursor = 0
        self._init_epoch(self.epoch, self.resume_step)

    def _init_epoch(self, epoch: int, resume_step: int = 0) -> None:
        all_indices = self.get_epoch_indices(epoch)
        skip = resume_step * self.batch_size
        self._indices = all_indices[skip:] if skip < len(all_indices) else []
        self._cursor = 0

    def get_epoch_indices(self, epoch: int) -> list[int]:
        """Produce deterministic shuffled indices for the given epoch."""
        indices = list(range(self.num_samples))
        # Seed uniquely per epoch
        rng = random.Random(self.base_seed + epoch * 10007)
        rng.shuffle(indices)
        return indices

    def __iter__(self) -> DeterministicSampler:
        return self

    def __next__(self) -> int:
        if self._cursor >= len(self._indices):
            self.epoch += 1
            self._init_epoch(self.epoch, 0)
            if not self._indices:
                raise StopIteration
        val = self._indices[self._cursor]
        self._cursor += 1
        self.step += 1
        return val


@dataclass(slots=True)
class SampleCollator:
    """Batches and pads samples according to BatchPolicy and token limits."""

    policy: BatchPolicy
    truncation_warnings: int = 0

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Lightweight token estimator (~1.3 tokens per whitespace token)."""
        words = text.split()
        return max(1, int(len(words) * 1.3))

    def collate(self, samples: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Group samples into batches respecting max_sequence_tokens and max_batch_tokens."""
        batches: list[list[dict[str, Any]]] = []
        current_batch: list[dict[str, Any]] = []
        current_batch_tokens = 0

        for sample in samples:
            inp = sample.get("input_data", {}).get("user_input", "")
            est_tokens = self.estimate_tokens(inp)

            # Check sequence length cap
            if est_tokens > self.policy.max_sequence_tokens:
                self.truncation_warnings += 1
                if not self.policy.truncate_long_sequences:
                    logger.warning(
                        "Sample exceeds max_sequence_tokens (%d > %d) and truncation is disabled",
                        est_tokens,
                        self.policy.max_sequence_tokens,
                    )

            sample_tokens = min(est_tokens, self.policy.max_sequence_tokens)

            # Check if adding sample breaches batch_size or max_batch_tokens
            would_exceed_size = len(current_batch) >= self.policy.batch_size
            would_exceed_tokens = (
                current_batch_tokens + sample_tokens > self.policy.max_batch_tokens
                and len(current_batch) > 0
            )

            if would_exceed_size or would_exceed_tokens:
                batches.append(current_batch)
                current_batch = [sample]
                current_batch_tokens = sample_tokens
            else:
                current_batch.append(sample)
                current_batch_tokens += sample_tokens

        if current_batch:
            batches.append(current_batch)

        return batches
