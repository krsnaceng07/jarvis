"""jarvis_learning.training.worker — supervised training worker child process.

Executes training loops in an isolated process boundary, emits periodic heartbeats,
respects cooperative pause requests at checkpoint boundaries, and reports metrics via IPC.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .batching import BatchPolicy, DeterministicSampler, SampleCollator
from .budget import BudgetTracker, TrainingBudget
from .checkpoint_store import CheckpointStore
from .cpu_governor import CpuGovernor
from .loss_tracker import LossTracker
from .trainer_backend import TrainerBackend, get_trainer_backend

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TrainingWorkerChild:
    """Worker child execution loop with IPC heartbeat and cooperative pausing."""

    job_id: str
    target: str
    dataset_dir: Path
    output_dir: Path
    budget: TrainingBudget
    batch_policy: BatchPolicy = field(default_factory=BatchPolicy)
    backend: TrainerBackend = field(default_factory=lambda: get_trainer_backend("tfidf_logistic"))
    pause_requested: bool = False
    cancel_requested: bool = False
    is_paused: bool = False

    def emit_ipc(self, msg_type: str, payload: dict[str, Any] | None = None) -> None:
        """Emit a structured JSON line message over stdout."""
        msg = {
            "type": msg_type,
            "job_id": self.job_id,
            "timestamp": time.time(),
            "payload": payload or {},
        }
        try:
            line = json.dumps(msg, separators=(",", ":"))
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except Exception:
            pass

    def run(self) -> bool:
        """Execute the supervised worker loop."""
        self.emit_ipc("STARTING", {"target": self.target})

        # Load samples
        train_path = self.dataset_dir / "train.jsonl"
        val_path = self.dataset_dir / "validation.jsonl"

        train_samples = self._load_jsonl(train_path)
        val_samples = self._load_jsonl(val_path)

        if not train_samples:
            self.emit_ipc("FAILED", {"reason": "No training samples found"})
            return False

        # Apply thread controls
        CpuGovernor().apply_runtime_thread_limits()

        # Initialize backend
        self.backend.initialize({"target": self.target, "learning_rate": 0.05})

        budget_tracker = BudgetTracker(budget=self.budget)
        loss_tracker = LossTracker()
        sampler = DeterministicSampler(base_seed=42, num_samples=len(train_samples))
        collator = SampleCollator(policy=self.batch_policy)

        self.emit_ipc("RUNNING")

        for epoch in range(self.budget.max_epochs):
            # Check for cooperative pause request at epoch/checkpoint boundary
            if self.pause_requested:
                self.is_paused = True
                self.emit_ipc("PAUSED", {"epoch": epoch})
                while self.pause_requested and not self.cancel_requested:
                    time.sleep(0.1)
                self.is_paused = False
                self.emit_ipc("RESUMED", {"epoch": epoch})

            if self.cancel_requested:
                self.emit_ipc("ABORTED", {"epoch": epoch})
                return False

            # Check budget
            exhaustion = budget_tracker.check_limits(raise_on_exhaustion=False)
            if exhaustion:
                self.emit_ipc("BUDGET_EXHAUSTED", {"reason": exhaustion.value})
                break

            # Shuffle and collate batches
            indices = sampler.get_epoch_indices(epoch)
            shuffled_samples = [train_samples[i] for i in indices]
            batches = collator.collate(shuffled_samples)

            epoch_loss = 0.0
            for batch in batches:
                # Check for mid-epoch pause/cancel
                if self.cancel_requested:
                    self.emit_ipc("ABORTED", {"epoch": epoch})
                    return False

                loss = self.backend.train_step(batch)
                epoch_loss += loss
                budget_tracker.record_step(tokens=len(batch) * 20, samples=len(batch))

                # Periodic heartbeat
                self.emit_ipc("HEARTBEAT")

            avg_train_loss = round(epoch_loss / max(1, len(batches)), 4)
            val_loss, val_acc = self.backend.evaluate(val_samples)
            budget_tracker.record_epoch()

            early_stop = loss_tracker.record_epoch(avg_train_loss, val_loss)

            self.emit_ipc(
                "PROGRESS",
                {
                    "epoch": epoch,
                    "train_loss": avg_train_loss,
                    "val_loss": val_loss,
                    "val_accuracy": val_acc,
                },
            )

            # Checkpoint at epoch boundary
            ckpt_name = f"checkpoint_epoch_{epoch:03d}"
            files_data = {"weights.json": json.dumps(self.backend.save_weights())}
            meta = {
                "checkpoint_id": ckpt_name,
                "epoch": epoch,
                "train_loss": avg_train_loss,
                "val_loss": val_loss,
                "target": self.target,
            }
            CheckpointStore.save_atomic_checkpoint(
                output_dir=self.output_dir,
                checkpoint_name=ckpt_name,
                files_data=files_data,
                metadata=meta,
            )
            budget_tracker.record_checkpoint(disk_mb_added=0.1)
            self.emit_ipc("CHECKPOINT", {"name": ckpt_name, "epoch": epoch})

            if early_stop:
                self.emit_ipc("EARLY_STOPPED", {"epoch": epoch})
                break

        self.emit_ipc("COMPLETED", {"epochs_trained": budget_tracker.epochs_completed})
        return True

    @staticmethod
    def _load_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        items = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    items.append(json.loads(stripped))
        return items


def main() -> None:
    """CLI entrypoint when worker is launched as a subprocess."""
    if len(sys.argv) < 5:
        sys.stderr.write("Usage: worker.py <job_id> <target> <dataset_dir> <output_dir>\n")
        sys.exit(1)

    job_id = sys.argv[1]
    target = sys.argv[2]
    dataset_dir = Path(sys.argv[3])
    output_dir = Path(sys.argv[4])

    worker = TrainingWorkerChild(
        job_id=job_id,
        target=target,
        dataset_dir=dataset_dir,
        output_dir=output_dir,
        budget=TrainingBudget(max_epochs=10),
    )
    success = worker.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
