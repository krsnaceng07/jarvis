"""jarvis_learning.evidence — Structured machine-readable evidence artifact generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RunManifest:
    """Run manifest identifying execution metadata, environment, and code version."""

    run_id: str
    timestamp_utc: str
    mode: str  # "deterministic" or "real-workspace"
    status: str  # "passed", "failed", "environment_unavailable", "not_proven"
    learning_effect: str  # "proven", "not_proven", "inconclusive"
    model_version: str = "v1.0.0"
    git_commit: str = "head"
    summary_metrics: dict[str, Any] = field(default_factory=dict)
    file_hashes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceRecorder:
    """Manages writing machine-readable evidence artifacts for a run."""

    def __init__(
        self, output_dir: str | Path, run_id: str = "run_default", mode: str = "deterministic"
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.mode = mode

        self.session_traces: list[dict[str, Any]] = []
        self.experience_records: list[dict[str, Any]] = []
        self.strategy_lineages: list[dict[str, Any]] = []
        self.runtime_decisions: list[dict[str, Any]] = []
        self.rollback_events: list[dict[str, Any]] = []
        self.model_evaluations: dict[str, Any] = {}
        self.benchmark_scorecards: dict[str, Any] = {}
        self.resource_usage: dict[str, Any] = {}

    def record_session_trace(self, trace_entry: dict[str, Any]) -> None:
        self.session_traces.append(trace_entry)

    def record_trace(self, trace_entry: dict[str, Any]) -> None:
        self.record_session_trace(trace_entry)

    def record_experience(self, exp_data: dict[str, Any]) -> None:
        self.experience_records.append(exp_data)

    def record_strategy_lineage(self, lineage_data: dict[str, Any]) -> None:
        self.strategy_lineages.append(lineage_data)

    def record_decision(self, decision_data: dict[str, Any]) -> None:
        self.runtime_decisions.append(decision_data)

    def record_rollback(self, rollback_data: dict[str, Any]) -> None:
        self.rollback_events.append(rollback_data)

    def set_model_evaluation(self, eval_data: dict[str, Any]) -> None:
        self.model_evaluations = dict(eval_data)

    def record_model_eval(self, eval_data: dict[str, Any]) -> None:
        self.set_model_evaluation(eval_data)

    def set_benchmark_scorecard(self, scorecard_data: dict[str, Any]) -> None:
        self.benchmark_scorecards = dict(scorecard_data)

    def record_benchmark_scorecard(self, scorecard_data: dict[str, Any]) -> None:
        self.set_benchmark_scorecard(scorecard_data)

    def set_resource_usage(self, resource_data: dict[str, Any]) -> None:
        self.resource_usage = dict(resource_data)

    def export_manifest(
        self,
        run_id: str | None = None,
        scenario: str | None = None,
        learning_effect: str = "proven",
        status: str = "passed",
        summary_metrics: dict[str, Any] | None = None,
    ) -> RunManifest:
        if run_id:
            self.run_id = run_id
        metrics = summary_metrics or {}
        if scenario:
            metrics["scenario"] = scenario
        return self.finalize_and_save(
            status=status, learning_effect=learning_effect, summary_metrics=metrics
        )

    def finalize_and_save(
        self,
        status: str,
        learning_effect: str,
        summary_metrics: dict[str, Any] | None = None,
    ) -> RunManifest:
        """Writes all structured evidence files and generates sha256 checksums."""
        now_str = datetime.now(timezone.utc).isoformat()
        manifest = RunManifest(
            run_id=self.run_id,
            timestamp_utc=now_str,
            mode=self.mode,
            status=status,
            learning_effect=learning_effect,
            summary_metrics=summary_metrics or {},
        )

        # 1. run_manifest.json
        (self.output_dir / "run_manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2), encoding="utf-8"
        )

        # 2. session_trace.jsonl
        with open(self.output_dir / "session_trace.jsonl", "w", encoding="utf-8") as f:
            for item in self.session_traces:
                f.write(json.dumps(item) + "\n")

        # 3. experience_records.jsonl
        with open(self.output_dir / "experience_records.jsonl", "w", encoding="utf-8") as f:
            for item in self.experience_records:
                f.write(json.dumps(item) + "\n")

        # 4. strategy_lineage.json
        (self.output_dir / "strategy_lineage.json").write_text(
            json.dumps(self.strategy_lineages, indent=2), encoding="utf-8"
        )

        # 5. runtime_decisions.jsonl
        with open(self.output_dir / "runtime_decisions.jsonl", "w", encoding="utf-8") as f:
            for item in self.runtime_decisions:
                f.write(json.dumps(item) + "\n")

        # 6. rollback_events.jsonl
        with open(self.output_dir / "rollback_events.jsonl", "w", encoding="utf-8") as f:
            for item in self.rollback_events:
                f.write(json.dumps(item) + "\n")

        # 7. model_evaluation.json
        (self.output_dir / "model_evaluation.json").write_text(
            json.dumps(self.model_evaluations, indent=2), encoding="utf-8"
        )

        # 8. benchmark_scorecard.json
        (self.output_dir / "benchmark_scorecard.json").write_text(
            json.dumps(self.benchmark_scorecards, indent=2), encoding="utf-8"
        )

        # 9. resource_usage.json
        (self.output_dir / "resource_usage.json").write_text(
            json.dumps(self.resource_usage, indent=2), encoding="utf-8"
        )

        # 10. checksums.json
        checksums: dict[str, str] = {}
        for p in self.output_dir.iterdir():
            if p.is_file() and p.name != "checksums.json":
                sha = hashlib.sha256(p.read_bytes()).hexdigest()
                checksums[p.name] = sha

        (self.output_dir / "checksums.json").write_text(
            json.dumps(checksums, indent=2), encoding="utf-8"
        )

        manifest = RunManifest(
            run_id=self.run_id,
            timestamp_utc=now_str,
            mode=self.mode,
            status=status,
            learning_effect=learning_effect,
            summary_metrics=summary_metrics or {},
            file_hashes=checksums,
        )
        return manifest
