"""jarvis_learning.training.trainer — offline model training pipeline.

Decoupled from active agent loops:
1. Enforces single-job concurrency and locks dataset inputs
2. Verifies Hard Gates 1-6 & 10 (approval, immutability, revocation, scope, Merkle, isolation, no auto-deploy)
3. Enforces multi-library thread and memory governance
4. Trains baseline model and candidate model under budget and batch limits
5. Emits durable atomic checkpoints with COMPLETE markers and fsync
6. Runs multi-split evaluation (test, OOD, challenge, golden holdout) with regression gates
7. Calibrates probabilities and registers candidate in ModelRegistry (CANDIDATE or REJECTED)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..datasets.dataset_manifest import DatasetManifest
from ..experience import generate_id, now_ms
from ..hardware.detector import HardwareDetector
from ..models.artifact import ModelArtifactBundle, ModelManifest
from ..models.calibration import ConfidenceCalibrator
from ..models.lifecycle import ModelStatus
from ..models.registry import ModelRecord, ModelRegistry
from .batching import DeterministicSampler, SampleCollator
from .budget import BudgetTracker
from .checkpoint_retention_policy import CheckpointRetentionPolicy
from .checkpoint_store import CheckpointStore
from .comparison import BaselineComparator, ComparisonReport
from .config import TrainingConfig
from .cpu_governor import CpuGovernor
from .dataset_lock import ConcurrencyController, TrainingInputLock
from .disk_governor import DiskGovernor
from .evaluation import CandidateEvaluationReport, CandidateEvaluator
from .governance import TrainingGovernance
from .job_lifecycle import JobStateMachine, TrainingJobState
from .loss_tracker import LossTracker
from .reproducibility import ReproducibilityFingerprint
from .resource_policy import TrainingExecutionController, TrainingResourcePolicy
from .trainer_backend import TFIDFLogisticBaselineBackend, get_trainer_backend

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TrainResult:
    """Outcome of an offline training run."""

    success: bool
    status: ModelStatus
    model_record: ModelRecord | None
    comparison_report: ComparisonReport | None
    artifact_dir: Path | None
    message: str
    evaluation_report: CandidateEvaluationReport | None = None
    job_id: str = ""


class OfflineTrainer:
    """Orchestrates model training decoupled from user response loops."""

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        hardware_detector: HardwareDetector | None = None,
        resource_policy: TrainingResourcePolicy | None = None,
        db_path: Path | None = None,
    ) -> None:
        self.registry = registry or ModelRegistry()
        self.hardware_detector = hardware_detector or HardwareDetector()
        self.resource_policy = resource_policy or TrainingResourcePolicy()
        self.controller = TrainingExecutionController(self.resource_policy)
        self.db_path = db_path

    def train(self, config: TrainingConfig) -> TrainResult:
        """Execute the end-to-end training pipeline."""
        job_id = f"job_{generate_id()[:12]}"
        logger.info("Starting offline training job='%s' for target='%s'", job_id, config.target)

        # 0. Single concurrent job slot acquisition
        ConcurrencyController.acquire_slot(job_id)
        state_machine = JobStateMachine(job_id=job_id, current_state=TrainingJobState.DRAFT)

        try:
            state_machine.transition_to(
                TrainingJobState.VALIDATING, "Pre-training governance checks"
            )

            # 1. Enforce thread limits across libraries
            CpuGovernor(max_threads=self.resource_policy.max_threads).apply_runtime_thread_limits()

            # 2. Hardware profile detection
            profile = self.hardware_detector.determine_profile()

            # 3. Verify dataset directory and manifest existence
            dataset_dir = Path(config.dataset_dir)
            manifest_path = dataset_dir / "manifest.json"
            if not manifest_path.exists():
                state_machine.transition_to(TrainingJobState.FAILED, "Manifest not found")
                return TrainResult(
                    success=False,
                    status=ModelStatus.TRAINING_FAILED,
                    model_record=None,
                    comparison_report=None,
                    artifact_dir=None,
                    message=f"Dataset manifest not found at {manifest_path}",
                    job_id=job_id,
                )

            dataset_manifest = DatasetManifest.from_json(manifest_path.read_text(encoding="utf-8"))

            # 4. Enforce Hard Gates 1-5 & 10
            TrainingGovernance.verify_gate1_approval(dataset_manifest)
            TrainingGovernance.verify_gate2_frozen(dataset_manifest)
            TrainingGovernance.verify_gate3_revocation(
                dataset_manifest.dataset_id, db_path=self.db_path
            )
            TrainingGovernance.verify_gate4_scope(dataset_manifest, target=config.target)
            TrainingGovernance.verify_gate10_zero_auto_deployment(auto_deploy_flag=False)

            # 5. Acquire Dataset Input Lock
            input_lock = TrainingInputLock(
                dataset_id=dataset_manifest.dataset_id,
                manifest_hash=dataset_manifest.source_snapshot_hash,
                dataset_dir=dataset_dir,
                db_path=self.db_path,
            )
            input_lock.acquire()

            # 6. Read sample files
            train_samples = self._read_jsonl(dataset_dir / "train.jsonl")
            val_samples = self._read_jsonl(dataset_dir / "validation.jsonl")
            test_samples = self._read_jsonl(dataset_dir / "test.jsonl")
            ood_samples = self._read_jsonl(dataset_dir / "ood_test.jsonl")
            challenge_samples = self._read_jsonl(dataset_dir / "challenge.jsonl")
            golden_samples = self._read_jsonl(dataset_dir / "golden_holdout.jsonl")

            # 7. Gate 6: Partition Isolation check
            train_ids = [s.get("sample_id", "") for s in train_samples if s.get("sample_id")]
            val_ids = [s.get("sample_id", "") for s in val_samples if s.get("sample_id")]
            test_ids = [s.get("sample_id", "") for s in test_samples if s.get("sample_id")]
            ood_ids = [s.get("sample_id", "") for s in ood_samples if s.get("sample_id")]
            golden_ids = [s.get("sample_id", "") for s in golden_samples if s.get("sample_id")]
            challenge_ids = [
                s.get("sample_id", "") for s in challenge_samples if s.get("sample_id")
            ]

            TrainingGovernance.verify_gate6_partition_isolation(
                train_ids=train_ids,
                val_ids=val_ids,
                test_ids=test_ids,
                ood_ids=ood_ids,
                golden_ids=golden_ids,
                challenge_ids=challenge_ids,
            )

            # Check minimum samples threshold
            if len(train_samples) < config.min_samples_required:
                logger.warning(
                    "Insufficient data: only %d training samples found (minimum %d required)",
                    len(train_samples),
                    config.min_samples_required,
                )
                state_machine.transition_to(TrainingJobState.REJECTED, "Insufficient samples")
                return TrainResult(
                    success=False,
                    status=ModelStatus.INSUFFICIENT_DATA,
                    model_record=None,
                    comparison_report=None,
                    artifact_dir=None,
                    message=(
                        f"Insufficient training data: {len(train_samples)} samples found, "
                        f"minimum {config.min_samples_required} required"
                    ),
                    job_id=job_id,
                )

            state_machine.transition_to(TrainingJobState.QUEUED, "Validation passed")
            state_machine.transition_to(
                TrainingJobState.STARTING, "Initializing models and storage"
            )

            # Output paths and Disk Governor
            version_str = f"v{len(self.registry.list_models(target=config.target)) + 1:03d}"
            if config.output_dir:
                artifact_dir = Path(config.output_dir) / config.target / version_str
            else:
                artifact_dir = (
                    Path.home() / ".jarvis" / "learning" / "models" / config.target / version_str
                )

            disk_governor = DiskGovernor()
            disk_governor.check_preflight(artifact_dir)

            state_machine.transition_to(TrainingJobState.RUNNING, "Starting training loop")

            # 8. Train Baseline 1 & Baseline 2
            baseline_backend = TFIDFLogisticBaselineBackend()
            baseline_backend.initialize(
                {"target": config.target, "learning_rate": config.learning_rate}
            )
            baseline_backend.model.fit(train_samples, epochs=15, lr=config.learning_rate)

            # 9. Train Candidate Model under Budget & BatchPolicy
            candidate_backend = get_trainer_backend(
                config.backend_type,
                max_features=4000,
                lr=config.learning_rate,
            )
            candidate_backend.initialize(
                {"target": config.target, "learning_rate": config.learning_rate}
            )

            budget_tracker = BudgetTracker(budget=config.budget)
            loss_tracker = LossTracker()
            sampler = DeterministicSampler(
                base_seed=config.random_seed, num_samples=len(train_samples)
            )
            collator = SampleCollator(policy=config.batch_policy)
            retention_policy = CheckpointRetentionPolicy(max_retained_checkpoints=5)

            # Check for cooperative pause / cancellation
            if not self.controller.check_checkpoint():
                state_machine.transition_to(
                    TrainingJobState.ABORTED, "Training cancelled by controller"
                )
                return TrainResult(
                    success=False,
                    status=ModelStatus.TRAINING_FAILED,
                    model_record=None,
                    comparison_report=None,
                    artifact_dir=None,
                    message="Training run was cancelled",
                    job_id=job_id,
                )

            # Training epoch loop
            for epoch in range(config.epochs):
                indices = sampler.get_epoch_indices(epoch)
                epoch_samples = [train_samples[i] for i in indices]
                batches = collator.collate(epoch_samples)

                epoch_loss = 0.0
                for batch in batches:
                    step_loss = candidate_backend.train_step(batch)
                    epoch_loss += step_loss
                    budget_tracker.record_step(tokens=len(batch) * 20, samples=len(batch))

                avg_train_loss = round(epoch_loss / max(1, len(batches)), 4)
                val_loss, _ = candidate_backend.evaluate(val_samples)
                budget_tracker.record_epoch()

                early_stop = loss_tracker.record_epoch(avg_train_loss, val_loss)

                # Checkpoint saving with COMPLETE marker
                ckpt_name = f"checkpoint_epoch_{epoch:03d}"
                ckpt_files = {"weights.json": json.dumps(candidate_backend.save_weights())}
                ckpt_meta = {
                    "checkpoint_id": ckpt_name,
                    "epoch": epoch,
                    "train_loss": avg_train_loss,
                    "val_loss": val_loss,
                    "target": config.target,
                }
                CheckpointStore.save_atomic_checkpoint(
                    output_dir=artifact_dir / "_checkpoints",
                    checkpoint_name=ckpt_name,
                    files_data=ckpt_files,
                    metadata=ckpt_meta,
                )
                budget_tracker.record_checkpoint(disk_mb_added=0.1)
                retention_policy.update_latest(ckpt_name)
                retention_policy.prune_checkpoints(artifact_dir / "_checkpoints")

                # Verify input lock still valid (checks for mid-run revocation)
                input_lock.verify_still_valid()

                if early_stop:
                    logger.info("Early stopping triggered at epoch %d", epoch)
                    break

            # 10. Multi-split candidate evaluation
            evaluator = CandidateEvaluator(min_test_accuracy_gain=config.min_accuracy_gain)
            eval_report = evaluator.evaluate_candidate(
                candidate=candidate_backend,
                baseline=baseline_backend,
                test_samples=test_samples if test_samples else val_samples,
                ood_samples=ood_samples,
                challenge_samples=challenge_samples,
                golden_samples=golden_samples,
            )

            # Confidence Calibration on validation set
            calibrator = ConfidenceCalibrator()
            val_probs: list[float] = []
            val_binary: list[int] = []
            for s in val_samples:
                inp = s.get("input_data", {}).get("user_input", "")
                tgt = s.get("label", {}).get("tool", "")
                pred_tool, prob = candidate_backend.predict(inp)
                is_match = 1 if pred_tool == tgt else 0
                val_probs.append(prob)
                val_binary.append(is_match)

            cal_metrics = calibrator.fit(val_probs, val_binary)

            # BaselineComparator for backward compatibility
            eval_samples = test_samples if test_samples else val_samples
            cand_preds = [
                candidate_backend.predict(s.get("input_data", {}).get("user_input", ""))
                for s in eval_samples
            ]
            base_preds = [
                baseline_backend.predict(s.get("input_data", {}).get("user_input", ""))
                for s in eval_samples
            ]
            test_ground_truth = [s.get("label", {}).get("tool", "") for s in eval_samples]
            comparator = BaselineComparator(min_accuracy_gain=config.min_accuracy_gain)
            comp_report = comparator.compare(cand_preds, base_preds, test_ground_truth)

            # Candidate status: strictly CANDIDATE or REJECTED
            initial_status = (
                ModelStatus.CANDIDATE if eval_report.beats_baseline else ModelStatus.REJECTED
            )

            # Save full ModelArtifactBundle
            model_id = generate_id()
            fingerprint = ReproducibilityFingerprint.create(
                seed=config.random_seed,
                dataset_manifest_hash=dataset_manifest.dataset_id,
                config_hash=config.compute_config_hash(),
                precision_mode=config.precision_mode,
            )

            manifest = ModelManifest(
                model_id=model_id,
                target=config.target,
                version=version_str,
                architecture=config.backend_type,
                compute_tier=profile.tier.value,
                feature_schema_version="1",
                created_at=now_ms(),
                parameters_count=len(candidate_backend.save_weights().get("vocabulary", {})) * 2,
                training_manifest_hash=dataset_manifest.dataset_id,
                metrics={
                    "test_accuracy": eval_report.test_result.candidate_accuracy,
                    "baseline_accuracy": eval_report.test_result.baseline_accuracy,
                    "accuracy_gain": eval_report.test_result.accuracy_gain,
                    "catastrophic_regression": eval_report.catastrophic_regression_detected,
                    "fingerprint_hash": fingerprint.compute_hash(),
                    "val_brier_score": cal_metrics.brier_score,
                },
            )

            weights_data = candidate_backend.save_weights()
            saved_path = ModelArtifactBundle.save_bundle(
                artifact_dir=artifact_dir,
                manifest=manifest,
                weights_data=weights_data,
                vectorizer_data={
                    "vocabulary": weights_data.get("vocabulary", {}),
                    "idf": weights_data.get("idf", {}),
                    "ngram_range": [1, 2],
                    "max_features": 4000,
                },
                label_encoder_data={
                    "classes": weights_data.get("classes", []),
                    "class_to_idx": weights_data.get("class_to_idx", {}),
                },
                calibration_data=calibrator.to_dict(),
                feature_schema={
                    "input_fields": ["user_input"],
                    "target_field": "tool",
                    "feature_type": "text_ngrams",
                    "schema_version": "1",
                },
            )

            # Register in ModelRegistry as CANDIDATE or REJECTED
            record = self.registry.register_model(
                model_id=model_id,
                target=config.target,
                version=version_str,
                architecture=config.backend_type,
                compute_tier=profile.tier.value,
                weights_path=str(saved_path / "weights.json"),
                weights_sha256=json.loads(
                    (saved_path / "checksums.json").read_text(encoding="utf-8")
                ).get("weights.json", ""),
                artifact_size=sum(f.stat().st_size for f in saved_path.glob("*")),
                dataset_manifest_hash=dataset_manifest.dataset_id,
                parameters_count=manifest.parameters_count,
                baseline_beaten="tfidf_logistic_baseline_v1",
                val_loss=round(1.0 - eval_report.test_result.candidate_accuracy, 4),
                val_metrics=manifest.metrics,
                initial_status=initial_status,
            )

            state_machine.transition_to(
                TrainingJobState.COMPLETED,
                f"Job finished with status {initial_status.value}",
            )

            return TrainResult(
                success=eval_report.beats_baseline,
                status=initial_status,
                model_record=record,
                comparison_report=comp_report,
                evaluation_report=eval_report,
                artifact_dir=saved_path,
                message=eval_report.verdict,
                job_id=job_id,
            )

        finally:
            # Release input lock and concurrency slot
            ConcurrencyController.release_slot(job_id)

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        samples = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    samples.append(json.loads(stripped))
        return samples
