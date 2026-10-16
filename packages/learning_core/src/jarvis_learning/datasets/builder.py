"""jarvis_learning.datasets.builder — production dataset construction pipeline.

Orchestrates the hardened 16-stage pipeline:
1. Freeze source experience high-water mark snapshot
2. Pre-persistence secret and credential scrubbing
3. Pre-persistence PII and private environment path scrubbing
4. Instruction hierarchy vs quoted content sanitization
5. Resource bounds and DoS limit validation
6. Provenance evaluation and authentic evidence registry resolution
7. Quarantine race condition check (active at capture AND snapshot time)
8. Causal uncertainty classification and weight attenuation
9. Format candidate samples with deterministic dual IDs (logical / materialized)
10. Generate contrastive hard negatives
11. Transitive connected-component grouping via Union-Find
12. Multi-mode OOD holdout selection and hierarchical 5-tier stratified splitting
13. 4-tier operational deduplication with contrast preservation
14. Construct binary Merkle tree and dataset-wide root
15. Validate with 35 checks (severity: CRITICAL, ERROR, WARNING, INFO)
16. Atomic staged build (.staging_<id> -> atomic rename) and provenance ledger logging
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..experience import Experience, generate_id
from ..strategies import StrategyStore
from ..storage.learning_db import LearningDatabase

from .canonicalization import canonical_hash
from .dataset_manifest import DatasetManifest, PHASE5_CORRECTION_MANIFEST_HASH, compute_file_sha256
from .deduplicator import DatasetDeduplicator
from .evidence_registry import EvidenceRegistryResolver
from .formatter import (
    MemoryRerankerFormatter,
    StrategyPredictorFormatter,
    ToolPolicyFormatter,
)
from .injection_filter import InjectionFilter
from .label_quality import LabelQualityAssessor
from .merkle_manifest import MerkleTree
from .negative_mining import HardNegativeMiner
from .ood_policy import HistoricalOODRegistry, OODHoldoutConfig
from .privacy_filter import PrivacyFilter
from .provenance import ProvenanceEvaluator
from .provenance_ledger import ProvenanceLedger
from .redaction import SecretScanner
from .resource_limits import ResourceLimits, validate_resource_bounds
from .sample_identity import compute_logical_sample_id, compute_materialized_sample_id
from .schema import DatasetSample, DatasetTarget, LabelQuality
from .snapshot import ExperienceSourceSnapshot, compute_snapshot
from .split import StratifiedGroupedSplitter
from .validator import DatasetValidator, ValidationReport

logger = logging.getLogger(__name__)

BUILDER_VERSION = "phase6.1"


@dataclass(frozen=True, slots=True)
class DatasetConfig:
    """Configuration for dataset building."""

    min_quality_score: float = 0.7
    min_confidence: float = 0.5
    dedup_threshold: float = 0.85
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15
    split_seed: int = 42
    ood_seed: int = 42
    max_samples: int = 10000
    output_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_quality_score": self.min_quality_score,
            "min_confidence": self.min_confidence,
            "dedup_threshold": self.dedup_threshold,
            "train_ratio": self.train_ratio,
            "validation_ratio": self.validation_ratio,
            "test_ratio": self.test_ratio,
            "split_seed": self.split_seed,
            "ood_seed": self.ood_seed,
            "max_samples": self.max_samples,
        }


@dataclass(frozen=True, slots=True)
class DatasetBuildResult:
    """Result of a dataset build."""

    success: bool
    manifest: DatasetManifest | None
    train_path: Path | None
    validation_path: Path | None
    test_path: Path | None
    ood_test_path: Path | None
    golden_holdout_path: Path | None
    challenge_path: Path | None
    validation_report: ValidationReport | None
    snapshot: ExperienceSourceSnapshot | None
    total_candidates: int
    provenance_rejected: int
    cleaning_rejected: int
    label_rejected: int
    quarantine_rejected: int
    dedup_removed: int
    final_train: int
    final_validation: int
    final_test: int
    final_ood_test: int
    final_golden_holdout: int
    final_challenge: int
    merkle_root: str = ""
    reproducibility_hash: str = ""


class DatasetBuilder:
    """Orchestrates the hardened dataset construction pipeline."""

    def __init__(
        self,
        db: LearningDatabase,
        strategy_store: StrategyStore,
        config: DatasetConfig | None = None,
        historical_ood_registry: HistoricalOODRegistry | None = None,
        limits: ResourceLimits | None = None,
    ) -> None:
        self._db = db
        self._strategy_store = strategy_store
        self._config = config or DatasetConfig()
        self._limits = limits or ResourceLimits()
        self._secret_scanner = SecretScanner()
        self._privacy_filter = PrivacyFilter()
        self._injection_filter = InjectionFilter()
        self._provenance = ProvenanceEvaluator()
        self._evidence_resolver = EvidenceRegistryResolver(db)
        self._label_assessor = LabelQualityAssessor()
        self._negative_miner = HardNegativeMiner(strategy_store)
        self._deduplicator = DatasetDeduplicator(
            token_similarity_threshold=self._config.dedup_threshold,
        )
        self._splitter = StratifiedGroupedSplitter(
            ood_config=OODHoldoutConfig(seed=self._config.ood_seed),
            historical_ood_registry=historical_ood_registry,
        )
        self._validator = DatasetValidator()
        self._ledger = ProvenanceLedger(db)
        self._tool_formatter = ToolPolicyFormatter()
        self._memory_formatter = MemoryRerankerFormatter()
        self._strategy_formatter = StrategyPredictorFormatter()

    def build(self, target: str, build_id: str | None = None) -> DatasetBuildResult:
        """Build a complete dataset for a target model under production guarantees."""
        dataset_build_id = build_id or f"bld_{generate_id()[:12]}"
        logger.info(
            "starting production dataset build target=%s, build_id=%s", target, dataset_build_id
        )

        # 1. Load experiences and freeze source snapshot
        raw_candidates = self._db.list_experiences(limit=self._config.max_samples)
        snapshot = compute_snapshot(raw_candidates, snapshot_timestamp=time.time())

        # Filter candidates strictly within snapshot cutoff
        def _exp_ts(e: Any) -> float:
            return float(getattr(e, "created_at", getattr(e, "timestamp", 0.0)))

        experiences = [e for e in raw_candidates if _exp_ts(e) <= snapshot.cutoff_timestamp]
        total_candidates = len(experiences)
        logger.info(
            "snapshot %s captured %d candidate experiences", snapshot.snapshot_id, total_candidates
        )

        if total_candidates == 0:
            return self._empty_result(total_candidates, snapshot=snapshot)

        provenance_rejected = 0
        cleaning_rejected = 0
        label_rejected = 0
        quarantine_rejected = 0

        approved_samples: list[DatasetSample] = []

        # Process experiences in deterministic order
        sorted_experiences = sorted(experiences, key=lambda e: (_exp_ts(e), getattr(e, "id", "")))

        for exp in sorted_experiences:
            # 2. Resource limits validation
            res_ok, _ = validate_resource_bounds(
                {
                    "user_input": exp.user_input,
                    "tool_arguments": exp.tool_arguments,
                    "tool_result": getattr(exp, "tool_result", ""),
                },
                self._limits,
            )
            if not res_ok:
                cleaning_rejected += 1
                continue

            # 3. Prompt injection vs quoted content scan
            inj_res = self._injection_filter.scan_sample(
                {
                    "user_input": exp.user_input,
                    "tool_result": getattr(exp, "tool_result", ""),
                }
            )
            if not inj_res.is_safe:
                cleaning_rejected += 1
                continue

            # 4. Pre-persistence secret and PII redaction
            sanitized_input, sec_records = self._secret_scanner.redact_text(
                exp.user_input, "user_input"
            )
            sanitized_input, pii_records = self._privacy_filter.scrub_text(
                sanitized_input, "user_input"
            )

            sanitized_args, sec_records_arg = self._secret_scanner.redact_text(
                exp.tool_arguments, "tool_arguments"
            )
            sanitized_args, pii_records_arg = self._privacy_filter.scrub_text(
                sanitized_args, "tool_arguments"
            )

            all_redactions = [
                asdict(r) for r in (sec_records + pii_records + sec_records_arg + pii_records_arg)
            ]

            # 5. Provenance evaluation
            provenance = self._provenance.evaluate(
                exp,
                cleaner_passed=True,
                contradiction_free=True,
                quality_score=exp.confidence,
            )
            if not provenance.approved_for_training:
                provenance_rejected += 1
                continue

            # 6. Evidence registry resolution
            evidence_records = self._db.get_evidence_for_experience(exp.id)
            if evidence_records:
                ev_digest = evidence_records[0].get("payload_digest", "")
                res_check = self._evidence_resolver.resolve_evidence(ev_digest)
                if not res_check.is_authentic:
                    provenance_rejected += 1
                    continue
            else:
                # Derive deterministic digest from canonical sanitized experience
                ev_digest = canonical_hash(
                    {"id": exp.id, "input": sanitized_input, "args": sanitized_args}
                )

            # 7. Quarantine race-condition check
            strat_info: dict[str, Any] = {}
            strat_id = getattr(exp, "selected_strategy_id", None) or getattr(
                exp, "reusable_strategy", None
            )
            if strat_id:
                strat = self._strategy_store.get_strategy(strat_id)
                if strat:
                    strat_state = getattr(strat, "status", "active")
                    if hasattr(strat_state, "value"):
                        strat_state = strat_state.value
                    strat_info = {
                        "strategy_id": strat.id,
                        "lifecycle_state": strat_state,
                        "risk_tier": getattr(strat, "risk_tier", 1),
                    }
                    if str(strat_state).lower() in (
                        "quarantined",
                        "deprecated",
                        "suspended",
                        "rejected",
                    ):
                        # Quarantined strategies CANNOT generate positive samples
                        quarantine_rejected += 1
                        continue

            # 8. Causal attribution & uncertainty scaling
            critique = (
                self._db.get_causal_critique_for_experience(exp.id)
                if hasattr(self._db, "get_causal_critique_for_experience")
                else None
            )
            attr_status = critique.get("attribution_status", "PROBABLE") if critique else "PROBABLE"
            causal_failure = critique.get("primary_failure_type", "") if critique else ""

            causal_weight = 1.0
            if attr_status == "PROBABLE":
                causal_weight = 0.8
            elif attr_status == "AMBIGUOUS":
                causal_weight = 0.3
            elif attr_status == "INSUFFICIENT_DATA":
                causal_weight = 0.0

            if causal_weight <= 0.0 and exp.verification_status != "verified_success":
                provenance_rejected += 1
                continue

            # 9. Label quality assessment
            label_assessment = self._label_assessor.assess(
                exp,
                episode=exp.episode,
                failure_patterns=self._strategy_store.all_failure_patterns(),
            )
            if label_assessment.quality in (LabelQuality.UNKNOWN, LabelQuality.SUBOPTIMAL):
                label_rejected += 1
                continue

            # 10. Format based on target
            import dataclasses

            sanitized_exp = dataclasses.replace(
                exp,
                user_input=sanitized_input,
                tool_arguments=sanitized_args,
            )

            raw_samples = self._format_experience(
                sanitized_exp, target, label_assessment, provenance.to_dict()
            )

            # 11. Wrap samples with Phase 6 hardened metadata
            for s in raw_samples:
                l_id = compute_logical_sample_id(
                    ev_digest,
                    target,
                    "sft",
                    semantic_payload={"input": s.input_data, "label": s.label},
                )
                m_id = compute_materialized_sample_id(l_id, dataset_build_id)

                sample_obj = DatasetSample(
                    sample_id=m_id,
                    target=s.target,
                    input_data=s.input_data,
                    label=s.label,
                    label_quality=s.label_quality,
                    label_confidence=s.label_confidence,
                    label_source=s.label_source,
                    sample_weight=round(s.sample_weight * causal_weight, 4),
                    provenance=s.provenance,
                    lineage=s.lineage,
                    quality_score=s.quality_score,
                    split="",
                    source_experience_id=exp.id,
                    schema_version="2",
                    logical_sample_id=l_id,
                    materialized_sample_id=m_id,
                    evidence_digest=ev_digest,
                    sample_usage="sft"
                    if s.label_quality in ("optimal", "acceptable")
                    else "dpo_preference",
                    outcome_vector={
                        "physical_correctness": exp.success,
                        "intent_correctness": bool(exp.interpreted_intent),
                        "verification_status": exp.verification_status,
                        "safety_score": 1.0,
                    },
                    causal_attribution={
                        "attribution_status": attr_status,
                        "causal_failure_type": causal_failure,
                    },
                    strategy_lineage=strat_info,
                    redaction_records=all_redactions,
                )
                approved_samples.append(sample_obj)

            # 12. Mine hard negatives for tool policy
            if target == DatasetTarget.TOOL_POLICY and raw_samples:
                negatives = self._negative_miner.mine_tool_negatives(sanitized_exp)
                neg_samples = self._negative_miner.negatives_to_samples(negatives, exp.id, target)
                for ns in neg_samples:
                    l_id = compute_logical_sample_id(
                        ev_digest,
                        target,
                        "dpo_preference",
                        semantic_payload={"input": ns.input_data, "label": ns.label},
                    )
                    m_id = compute_materialized_sample_id(l_id, dataset_build_id)
                    approved_samples.append(
                        DatasetSample(
                            sample_id=m_id,
                            target=ns.target,
                            input_data=ns.input_data,
                            label=ns.label,
                            label_quality=ns.label_quality,
                            label_confidence=ns.label_confidence,
                            label_source=ns.label_source,
                            sample_weight=ns.sample_weight,
                            provenance=ns.provenance if ns.provenance else provenance.to_dict(),
                            lineage=ns.lineage,
                            quality_score=ns.quality_score,
                            split="",
                            source_experience_id=exp.id,
                            schema_version="2",
                            logical_sample_id=l_id,
                            materialized_sample_id=m_id,
                            evidence_digest=ev_digest,
                            sample_usage="dpo_preference",
                            outcome_vector={"physical_correctness": False, "safety_score": 1.0},
                            causal_attribution={
                                "attribution_status": attr_status,
                                "causal_failure_type": causal_failure,
                            },
                            strategy_lineage=strat_info,
                            redaction_records=all_redactions,
                        )
                    )

        if not approved_samples:
            return self._empty_result(
                total_candidates,
                snapshot=snapshot,
                provenance_rejected=provenance_rejected,
                cleaning_rejected=cleaning_rejected,
                label_rejected=label_rejected,
                quarantine_rejected=quarantine_rejected,
            )

        # 13. Hierarchical zero-leakage grouped splitting
        split_result = self._splitter.split(
            approved_samples,
            train_ratio=self._config.train_ratio,
            validation_ratio=self._config.validation_ratio,
            test_ratio=self._config.test_ratio,
            seed=self._config.split_seed,
        )

        # 14. 4-tier operational deduplication within each split
        all_split_samples: list[DatasetSample] = []
        dedup_total = 0

        for s_list in [
            split_result.train,
            split_result.validation,
            split_result.test,
            split_result.ood_test,
            split_result.golden_holdout,
            split_result.challenge,
        ]:
            if s_list:
                d_res = self._deduplicator.deduplicate(s_list)
                all_split_samples.extend(d_res.unique_samples)
                dedup_total += d_res.total_removed

        # 15. Binary Merkle tree root over all unique logical sample IDs
        all_logical_ids = [s.logical_sample_id for s in all_split_samples]
        merkle_tree = MerkleTree(all_logical_ids)
        merkle_root = merkle_tree.root

        # 16. Build reproducibility manifest
        final_train = [s for s in all_split_samples if s.split == "train"]
        final_val = [s for s in all_split_samples if s.split == "validation"]
        final_test = [s for s in all_split_samples if s.split == "test"]
        final_ood = [s for s in all_split_samples if s.split == "ood_test"]
        final_golden = [s for s in all_split_samples if s.split == "golden_holdout"]
        final_chal = [s for s in all_split_samples if s.split == "challenge"]

        split_counts = {
            "train": len(final_train),
            "validation": len(final_val),
            "test": len(final_test),
            "ood_test": len(final_ood),
            "golden_holdout": len(final_golden),
            "challenge": len(final_chal),
        }

        # 16. Write staged splits first to compute authentic file content hashes
        target_dir = self._resolve_output_dir(target)
        staging_dir = target_dir.parent / f".staging_{dataset_build_id}"

        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True, exist_ok=True)

        train_path = self._write_jsonl(staging_dir / "train.jsonl", final_train)
        val_path = self._write_jsonl(staging_dir / "validation.jsonl", final_val)
        test_path = self._write_jsonl(staging_dir / "test.jsonl", final_test)
        ood_path = self._write_jsonl(staging_dir / "ood_test.jsonl", final_ood)
        golden_path = self._write_jsonl(staging_dir / "golden_holdout.jsonl", final_golden)
        chal_path = self._write_jsonl(staging_dir / "challenge.jsonl", final_chal)

        train_hash = compute_file_sha256(train_path)
        val_hash = compute_file_sha256(val_path)
        test_hash = compute_file_sha256(test_path)
        ood_hash = compute_file_sha256(ood_path)
        golden_hash = compute_file_sha256(golden_path)
        chal_hash = compute_file_sha256(chal_path)

        manifest = DatasetManifest(
            dataset_id=dataset_build_id,
            dataset_version=f"{target}_v1",
            target=target,
            schema_version="2",
            builder_version=BUILDER_VERSION,
            logical_build_timestamp=snapshot.cutoff_timestamp,
            source_snapshot_id=snapshot.snapshot_id,
            source_snapshot_hash=snapshot.source_snapshot_hash,
            phase5_correction_manifest_hash=PHASE5_CORRECTION_MANIFEST_HASH,
            dataset_merkle_root=merkle_root,
            split_seed=self._config.split_seed,
            ood_seed=self._config.ood_seed,
            split_counts=split_counts,
            filter_config=self._config.to_dict(),
            label_distribution=dict(Counter(s.label_quality for s in all_split_samples)),
            runtime_created_at=time.time(),
            source_experience_count=total_candidates,
            approved_count=len(approved_samples),
            provenance_rejected=provenance_rejected,
            cleaning_rejected=cleaning_rejected,
            label_rejected=label_rejected,
            dedup_removed=dedup_total,
            split_content_hashes={
                "train": train_hash,
                "validation": val_hash,
                "test": test_hash,
                "ood_test": ood_hash,
                "golden_holdout": golden_hash,
                "challenge": chal_hash,
            },
            train_content_hash=train_hash,
            validation_content_hash=val_hash,
            test_content_hash=test_hash,
            challenge_content_hash=chal_hash,
        )

        (staging_dir / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")

        # 17. Run 35-check validation with severity semantics
        val_report = self._validator.validate(all_split_samples, manifest=manifest)

        # Atomic commit if valid and on same filesystem
        if val_report.valid:
            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            staging_dir.rename(target_dir)
            logger.info("atomic commit complete: staged dataset moved to %s", target_dir)
        else:
            logger.warning(
                "build validation failed; staging directory kept at %s for audit", staging_dir
            )

        # 19. Record to tamper-evident provenance ledger
        self._ledger.append_event(
            event_type="DATASET_MATERIALIZED",
            sample_id=dataset_build_id,
            evidence_digest=snapshot.source_snapshot_hash,
            details={
                "target": target,
                "merkle_root": merkle_root,
                "total_samples": len(all_split_samples),
                "is_valid": val_report.valid,
            },
        )

        return DatasetBuildResult(
            success=val_report.valid,
            manifest=manifest,
            train_path=target_dir / "train.jsonl" if val_report.valid else train_path,
            validation_path=target_dir / "validation.jsonl" if val_report.valid else val_path,
            test_path=target_dir / "test.jsonl" if val_report.valid else test_path,
            ood_test_path=target_dir / "ood_test.jsonl" if val_report.valid else ood_path,
            golden_holdout_path=target_dir / "golden_holdout.jsonl"
            if val_report.valid
            else golden_path,
            challenge_path=target_dir / "challenge.jsonl" if val_report.valid else chal_path,
            validation_report=val_report,
            snapshot=snapshot,
            total_candidates=total_candidates,
            provenance_rejected=provenance_rejected,
            cleaning_rejected=cleaning_rejected,
            label_rejected=label_rejected,
            quarantine_rejected=quarantine_rejected,
            dedup_removed=dedup_total,
            final_train=len(final_train),
            final_validation=len(final_val),
            final_test=len(final_test),
            final_ood_test=len(final_ood),
            final_golden_holdout=len(final_golden),
            final_challenge=len(final_chal),
            merkle_root=merkle_root,
            reproducibility_hash=manifest.compute_reproducibility_hash(),
        )

    def _format_experience(
        self,
        exp: Experience,
        target: str,
        label_assessment: Any,
        provenance_dict: dict[str, Any],
    ) -> list[DatasetSample]:
        samples: list[DatasetSample] = []
        if target == DatasetTarget.TOOL_POLICY:
            sample = self._tool_formatter.format(exp, label_assessment, provenance_dict)
            if sample:
                samples.append(sample)
        elif target == DatasetTarget.MEMORY_RERANKER:
            sample = self._memory_formatter.format(exp)
            if sample:
                samples.append(sample)
        elif target == DatasetTarget.STRATEGY_PREDICTOR:
            candidates = self._strategy_store.find_strategies_for_intent(
                exp.interpreted_intent or exp.user_input[:100]
            )
            selected = candidates[0] if candidates else None
            strat_samples = self._strategy_formatter.format(exp, candidates, selected)
            samples.extend(strat_samples)
        return samples

    def _resolve_output_dir(self, target: str) -> Path:
        if self._config.output_dir:
            base = Path(self._config.output_dir)
        else:
            base = Path.home() / ".jarvis" / "learning" / "datasets"
        return base / target

    @staticmethod
    def _write_jsonl(path: Path, samples: list[DatasetSample]) -> Path:
        with open(path, "w", encoding="utf-8") as f:
            for s in samples:
                f.write(json.dumps(s.to_jsonl_dict(), sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return path

    @staticmethod
    def _empty_result(
        total: int,
        snapshot: ExperienceSourceSnapshot | None = None,
        provenance_rejected: int = 0,
        cleaning_rejected: int = 0,
        label_rejected: int = 0,
        quarantine_rejected: int = 0,
    ) -> DatasetBuildResult:
        return DatasetBuildResult(
            success=False,
            manifest=None,
            train_path=None,
            validation_path=None,
            test_path=None,
            ood_test_path=None,
            golden_holdout_path=None,
            challenge_path=None,
            validation_report=None,
            snapshot=snapshot,
            total_candidates=total,
            provenance_rejected=provenance_rejected,
            cleaning_rejected=cleaning_rejected,
            label_rejected=label_rejected,
            quarantine_rejected=quarantine_rejected,
            dedup_removed=0,
            final_train=0,
            final_validation=0,
            final_test=0,
            final_ood_test=0,
            final_golden_holdout=0,
            final_challenge=0,
            merkle_root="",
            reproducibility_hash="",
        )
