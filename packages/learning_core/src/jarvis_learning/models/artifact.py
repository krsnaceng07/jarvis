"""jarvis_learning.models.artifact — multi-file model artifact storage and integrity.

Manages the bundle of files needed for complete, reproducible inference:
- model weights / parameters
- vocabulary / vectorizer
- label encoder mapping
- confidence calibration parameters
- feature schema definition
- manifest & SHA-256 checksums
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import ModelTargetMismatchError


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True, slots=True)
class ModelManifest:
    """Metadata describing a saved model artifact bundle."""

    model_id: str
    target: str
    version: str
    architecture: str
    compute_tier: str
    feature_schema_version: str
    created_at: int
    parameters_count: int
    training_manifest_hash: str
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "target": self.target,
            "version": self.version,
            "architecture": self.architecture,
            "compute_tier": self.compute_tier,
            "feature_schema_version": self.feature_schema_version,
            "created_at": self.created_at,
            "parameters_count": self.parameters_count,
            "training_manifest_hash": self.training_manifest_hash,
            "metrics": self.metrics,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ModelManifest:
        return cls(
            model_id=d["model_id"],
            target=d["target"],
            version=d["version"],
            architecture=d["architecture"],
            compute_tier=d.get("compute_tier", "fallback"),
            feature_schema_version=d.get("feature_schema_version", "1"),
            created_at=int(d.get("created_at", 0)),
            parameters_count=int(d.get("parameters_count", 0)),
            training_manifest_hash=d.get("training_manifest_hash", ""),
            metrics=d.get("metrics", {}),
        )


class ModelArtifactBundle:
    """Saves, verifies, and loads a versioned model artifact package."""

    REQUIRED_FILES = (
        "manifest.json",
        "checksums.json",
        "calibration.json",
        "feature_schema.json",
        "label_encoder.json",
    )

    @classmethod
    def save_bundle(
        cls,
        artifact_dir: Path,
        manifest: ModelManifest,
        weights_data: dict[str, Any] | bytes,
        vectorizer_data: dict[str, Any],
        label_encoder_data: dict[str, Any],
        calibration_data: dict[str, Any],
        feature_schema: dict[str, Any],
    ) -> Path:
        """Serialize complete model package to disk with cryptographic checksums."""
        artifact_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write payload files
        if isinstance(weights_data, bytes):
            (artifact_dir / "model.bin").write_bytes(weights_data)
        else:
            (artifact_dir / "weights.json").write_text(
                json.dumps(weights_data, indent=2, sort_keys=True), encoding="utf-8"
            )

        (artifact_dir / "vectorizer.json").write_text(
            json.dumps(vectorizer_data, indent=2, sort_keys=True), encoding="utf-8"
        )
        (artifact_dir / "label_encoder.json").write_text(
            json.dumps(label_encoder_data, indent=2, sort_keys=True), encoding="utf-8"
        )
        (artifact_dir / "calibration.json").write_text(
            json.dumps(calibration_data, indent=2, sort_keys=True), encoding="utf-8"
        )
        (artifact_dir / "feature_schema.json").write_text(
            json.dumps(feature_schema, indent=2, sort_keys=True), encoding="utf-8"
        )
        (artifact_dir / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
        )

        # 2. Compute checksums for all files except checksums.json
        checksums: dict[str, str] = {}
        for file_path in sorted(artifact_dir.glob("*")):
            if file_path.name != "checksums.json" and file_path.is_file():
                checksums[file_path.name] = compute_sha256(file_path)

        (artifact_dir / "checksums.json").write_text(
            json.dumps(checksums, indent=2, sort_keys=True), encoding="utf-8"
        )

        return artifact_dir

    @classmethod
    def verify_and_load(
        cls, artifact_dir: Path, expected_target: str
    ) -> tuple[ModelManifest, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Verify artifact integrity and return contents.

        Raises ModelTargetMismatchError if target doesn't match.
        Raises ValueError if checksum verification fails.
        """
        if not artifact_dir.exists() or not artifact_dir.is_dir():
            raise FileNotFoundError(f"Artifact directory does not exist: {artifact_dir}")

        checksums_path = artifact_dir / "checksums.json"
        if not checksums_path.exists():
            raise ValueError(f"Missing checksums.json in artifact bundle: {artifact_dir}")

        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))

        # Verify all file hashes
        for filename, expected_hash in checksums.items():
            path = artifact_dir / filename
            if not path.exists():
                raise FileNotFoundError(f"Missing expected artifact file: {filename}")
            actual_hash = compute_sha256(path)
            if actual_hash != expected_hash:
                raise ValueError(
                    f"Integrity check failed for {filename}: expected {expected_hash}, got {actual_hash}"
                )

        # Load and verify manifest target
        manifest = ModelManifest.from_dict(
            json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
        )
        if manifest.target != expected_target:
            raise ModelTargetMismatchError(
                f"Model target mismatch: expected '{expected_target}', artifact is for '{manifest.target}'"
            )

        vectorizer_data = json.loads((artifact_dir / "vectorizer.json").read_text(encoding="utf-8"))
        label_encoder_data = json.loads(
            (artifact_dir / "label_encoder.json").read_text(encoding="utf-8")
        )
        calibration_data = json.loads(
            (artifact_dir / "calibration.json").read_text(encoding="utf-8")
        )
        feature_schema = json.loads(
            (artifact_dir / "feature_schema.json").read_text(encoding="utf-8")
        )

        return manifest, vectorizer_data, label_encoder_data, calibration_data, feature_schema
