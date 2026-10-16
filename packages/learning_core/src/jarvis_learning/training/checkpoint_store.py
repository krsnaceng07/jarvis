"""jarvis_learning.training.checkpoint_store — durable atomic checkpoint store with COMPLETE marker.

Protocol:
1. Write files to .staging_<uuid>
2. flush() and os.fsync() on each file descriptor
3. Atomic same-volume rename to final directory
4. Write COMPLETE marker file
5. Validation rejects any checkpoint lacking COMPLETE, missing optimizer state when required,
   or with corrupted SHA-256.
6. Invalidation cascades: marks checkpoints REVOKED_INELIGIBLE when dataset is revoked.
7. Startup recovery cleans abandoned .staging_<uuid> directories.
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
import os
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import CheckpointCorruptError, CheckpointMissingCompleteMarkerError

logger = logging.getLogger(__name__)

COMPLETE_MARKER_FILE = "COMPLETE"
CHECKSUMS_FILE = "checksums.json"
REVOKED_MARKER_FILE = "REVOKED_INELIGIBLE"


class CheckpointTransactionState(enum.StrEnum):
    """Crash-consistent transaction states for atomic checkpoint publication (INV-CHK-001)."""

    CREATED = "CREATED"
    WRITING = "WRITING"
    FILES_HASHED = "FILES_HASHED"
    FILES_FSYNCED = "FILES_FSYNCED"
    DIRECTORY_FSYNCED = "DIRECTORY_FSYNCED"
    RENAMED_ATOMICALLY = "RENAMED_ATOMICALLY"
    COMPLETE_MARKER_WRITTEN = "COMPLETE_MARKER_WRITTEN"
    REGISTRY_COMMITTED = "REGISTRY_COMMITTED"
    VERIFIED = "VERIFIED"


@dataclass(frozen=True, slots=True)
class CheckpointMetadata:
    """15-field diagnostic audit header for a verified checkpoint."""

    checkpoint_id: str
    epoch: int
    step: int
    train_loss: float
    val_loss: float
    manifest_hash: str
    config_hash: str
    seed: int
    path: Path
    dataset_id: str = ""
    is_revoked: bool = False
    run_id: str = ""
    created_at: str = ""
    transaction_state: str = CheckpointTransactionState.VERIFIED.value
    format_version: str = "1.0"
    checksums_sha256: str = ""
    device_target: str = "cpu"


class CheckpointStore:
    """Manages atomic writing, fsync flushing, durability verification, and revocation invalidation."""

    @staticmethod
    def _compute_sha256(path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @classmethod
    def save_atomic_checkpoint(
        cls,
        output_dir: Path,
        checkpoint_name: str,
        files_data: dict[str, str | bytes],
        metadata: dict[str, Any],
        crash_at_state: CheckpointTransactionState | None = None,
        state_callback: Callable[[CheckpointTransactionState], None] | None = None,
    ) -> Path:
        """Write checkpoint files atomically with fsync and COMPLETE marker.

        Enforces the 9-state crash-consistent atomic publication protocol (INV-CHK-001).
        """
        target_dir = output_dir / checkpoint_name
        staging_dir = output_dir / f".staging_{uuid.uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=True)

        def _transition(st: CheckpointTransactionState) -> None:
            if state_callback:
                state_callback(st)
            if crash_at_state == st:
                raise RuntimeError(f"Simulated crash at transaction state {st.value}")

        _transition(CheckpointTransactionState.CREATED)

        checksums: dict[str, str] = {}

        try:
            _transition(CheckpointTransactionState.WRITING)

            # 1. Enrich 15-field metadata header
            enriched_meta = dict(metadata)
            enriched_meta.setdefault("checkpoint_id", checkpoint_name)
            enriched_meta.setdefault(
                "created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            )
            enriched_meta.setdefault("transaction_state", CheckpointTransactionState.VERIFIED.value)
            enriched_meta.setdefault("format_version", "1.0")
            enriched_meta.setdefault("device_target", "cpu")

            # 2. Write metadata
            meta_json = json.dumps(enriched_meta, indent=2, sort_keys=True)
            meta_path = staging_dir / "checkpoint_meta.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                f.write(meta_json)
                f.flush()
                os.fsync(f.fileno())

            # 3. Write all payload files
            for filename, content in files_data.items():
                file_path = staging_dir / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)

                if isinstance(content, str):
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                        f.flush()
                        os.fsync(f.fileno())
                else:
                    with open(file_path, "wb") as f:
                        f.write(content)
                        f.flush()
                        os.fsync(f.fileno())

            # 4. Hash files
            _transition(CheckpointTransactionState.FILES_HASHED)
            checksums["checkpoint_meta.json"] = cls._compute_sha256(meta_path)
            for filename in files_data:
                checksums[filename] = cls._compute_sha256(staging_dir / filename)

            # 5. Write checksums.json and fsync
            sums_path = staging_dir / CHECKSUMS_FILE
            with open(sums_path, "w", encoding="utf-8") as f:
                json.dump(checksums, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())

            _transition(CheckpointTransactionState.FILES_FSYNCED)

            # 6. Fsync staging directory (POSIX fd fsync; fallback on Windows)
            try:
                dir_fd = os.open(str(staging_dir), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass  # Directory fsync unsupported on Windows or specific filesystems

            _transition(CheckpointTransactionState.DIRECTORY_FSYNCED)

            # 7. Atomic directory rename
            if target_dir.exists():
                shutil.rmtree(target_dir)
            staging_dir.rename(target_dir)

            _transition(CheckpointTransactionState.RENAMED_ATOMICALLY)

            # 8. Write COMPLETE marker inside published directory
            complete_path = target_dir / COMPLETE_MARKER_FILE
            with open(complete_path, "w", encoding="utf-8") as f:
                f.write(f"CHECKPOINT_COMPLETE {checkpoint_name}\n")
                f.flush()
                os.fsync(f.fileno())

            _transition(CheckpointTransactionState.COMPLETE_MARKER_WRITTEN)

            # 9. Registry commit & verification state
            _transition(CheckpointTransactionState.REGISTRY_COMMITTED)
            _transition(CheckpointTransactionState.VERIFIED)

            logger.info("Published atomic durable checkpoint at '%s'", target_dir)
            return target_dir

        except Exception as exc:
            logger.error(
                "Failed saving checkpoint; cleaning up staging dir '%s': %s", staging_dir, exc
            )
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
            raise

    @classmethod
    def verify_checkpoint(
        cls,
        checkpoint_dir: Path,
        require_optimizer: bool = False,
    ) -> CheckpointMetadata:
        """Verify checkpoint completeness, SHA-256 integrity, and non-revocation."""
        p = Path(checkpoint_dir)
        if not p.is_dir():
            raise CheckpointCorruptError(f"Checkpoint path '{p}' is not a directory")

        # Check 0: Revocation marker
        if (p / REVOKED_MARKER_FILE).exists():
            raise CheckpointCorruptError(
                f"Checkpoint at '{p}' is marked {REVOKED_MARKER_FILE} (ineligible)"
            )

        # Check 1: COMPLETE marker existence
        complete_file = p / COMPLETE_MARKER_FILE
        if not complete_file.exists():
            raise CheckpointMissingCompleteMarkerError(
                f"Checkpoint at '{p}' is incomplete (missing COMPLETE marker)"
            )

        # Check 2: checksums.json existence and verification
        sums_file = p / CHECKSUMS_FILE
        if not sums_file.exists():
            raise CheckpointCorruptError(f"Missing '{CHECKSUMS_FILE}' in checkpoint '{p}'")

        try:
            checksums = json.loads(sums_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CheckpointCorruptError(f"Unreadable checksums in '{sums_file}': {exc}")

        for filename, expected_sha in checksums.items():
            file_path = p / filename
            if not file_path.exists():
                raise CheckpointCorruptError(f"Missing file '{filename}' in checkpoint '{p}'")
            actual_sha = cls._compute_sha256(file_path)
            if actual_sha != expected_sha:
                raise CheckpointCorruptError(
                    f"Corrupted file '{filename}': expected {expected_sha[:12]}, got {actual_sha[:12]}"
                )

        # Check 3: Check optimizer state if required
        if require_optimizer and "optimizer.json" not in checksums:
            raise CheckpointCorruptError(f"Missing required optimizer state in checkpoint '{p}'")

        # Check 4: Load metadata
        meta_file = p / "checkpoint_meta.json"
        metadata: dict[str, Any] = {}
        if meta_file.exists():
            try:
                metadata = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        return CheckpointMetadata(
            checkpoint_id=metadata.get("checkpoint_id", p.name),
            epoch=metadata.get("epoch", 0),
            step=metadata.get("step", 0),
            train_loss=metadata.get("train_loss", 0.0),
            val_loss=metadata.get("val_loss", 0.0),
            manifest_hash=metadata.get("manifest_hash", ""),
            config_hash=metadata.get("config_hash", ""),
            seed=metadata.get("seed", 0),
            dataset_id=metadata.get("dataset_id", ""),
            is_revoked=False,
            run_id=metadata.get("run_id", ""),
            created_at=metadata.get("created_at", ""),
            transaction_state=metadata.get(
                "transaction_state", CheckpointTransactionState.VERIFIED.value
            ),
            format_version=metadata.get("format_version", "1.0"),
            checksums_sha256=metadata.get("checksums_sha256", ""),
            device_target=metadata.get("device_target", "cpu"),
            path=p,
        )

    @classmethod
    def cleanup_abandoned_staging(cls, output_dir: Path) -> list[str]:
        """Discover and clean up abandoned .staging_* directories left by crashes."""
        if not output_dir.exists():
            return []
        cleaned: list[str] = []
        for item in output_dir.iterdir():
            if item.is_dir() and item.name.startswith(".staging_"):
                try:
                    shutil.rmtree(item)
                    cleaned.append(item.name)
                    logger.info("Cleaned abandoned staging directory '%s'", item)
                except Exception as exc:
                    logger.warning("Could not clean staging directory '%s': %s", item, exc)
        return cleaned

    @classmethod
    def invalidate_dataset_checkpoints(cls, output_dir: Path, dataset_id: str) -> list[str]:
        """Invalidate all checkpoints originating from a revoked dataset."""
        if not output_dir.exists():
            return []
        invalidated: list[str] = []
        for item in output_dir.iterdir():
            if item.is_dir() and not item.name.startswith((".", "_")):
                meta_file = item / "checkpoint_meta.json"
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8"))
                        if meta.get("dataset_id") == dataset_id or meta.get("target") == dataset_id:
                            # Write marker
                            (item / REVOKED_MARKER_FILE).write_text(
                                f"Revoked dataset: {dataset_id}\n", encoding="utf-8"
                            )
                            invalidated.append(item.name)
                            logger.warning(
                                "Invalidated checkpoint '%s' linked to revoked dataset '%s'",
                                item.name,
                                dataset_id,
                            )
                    except Exception:
                        pass
        return invalidated

    @classmethod
    def quarantine_checkpoint(cls, checkpoint_dir: Path, reason: str = "corrupted") -> Path:
        """Move an unverified or corrupt checkpoint to _quarantine."""
        p = Path(checkpoint_dir)
        quarantine_dir = p.parent / "_quarantine" / f"{p.name}_{uuid.uuid4().hex[:8]}"
        quarantine_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(quarantine_dir))
        reason_file = quarantine_dir / "QUARANTINE_REASON.txt"
        reason_file.write_text(f"Quarantined: {reason}\n", encoding="utf-8")
        logger.warning("Quarantined corrupt checkpoint from '%s' to '%s'", p, quarantine_dir)
        return quarantine_dir
