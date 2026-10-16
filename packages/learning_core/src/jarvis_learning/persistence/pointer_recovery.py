"""Active pointer generation/epoch tracker and rollback recovery engine.

Guarantees epoch continuity: if an interrupted update leaves an invalid generation
in the active pointer, recovery safely rolls back to the latest verified durable generation.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from jarvis_learning.persistence.models import PointerState

logger = logging.getLogger(__name__)


class ActivePointerManager:
    """Manages active pointer updates, SHA-256 verification, and epoch rollback."""

    POINTER_FILE = "ACTIVE_POINTER.json"

    @classmethod
    def read_pointer(cls, root_dir: Path) -> PointerState | None:
        path = root_dir / cls.POINTER_FILE
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PointerState(**data)
        except Exception:
            return None

    @classmethod
    def write_pointer(cls, root_dir: Path, state: PointerState) -> Path:
        root_dir.mkdir(parents=True, exist_ok=True)
        path = root_dir / cls.POINTER_FILE
        path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def verify_and_recover(
        cls,
        root_dir: Path,
    ) -> tuple[PointerState | None, str, bool]:
        """Verify active pointer points to valid artifact, or rollback to last durable generation.

        Returns (effective_pointer, status_reason, rollback_performed).
        """
        current_ptr = cls.read_pointer(root_dir)
        artifacts_dir = root_dir / "artifacts"

        # Check if current pointer is valid
        if current_ptr is not None:
            target_file = artifacts_dir / f"{current_ptr.artifact_id}.bin"
            if target_file.exists():
                actual_digest = hashlib.sha256(target_file.read_bytes()).hexdigest()
                if actual_digest == current_ptr.sha256:
                    return current_ptr, "ACTIVE_POINTER_VALID", False

        # Current pointer is invalid, corrupted, or missing -> attempt generation rollback
        logger.warning("Active pointer invalid or corrupted. Attempting epoch rollback.")
        valid_generations: list[PointerState] = []

        if artifacts_dir.exists():
            # Scan available artifacts for valid ledgers
            for ledger in artifacts_dir.glob("**/commit_ledger.json"):
                try:
                    data = json.loads(ledger.read_text(encoding="utf-8"))
                    gen = int(data.get("generation", 0))
                    art_id = str(data.get("artifact_id", ""))
                    expected_digest = str(data.get("sha256", ""))
                    bin_file = ledger.parent / f"{art_id}.bin"

                    if bin_file.exists():
                        actual_digest = hashlib.sha256(bin_file.read_bytes()).hexdigest()
                        if actual_digest == expected_digest:
                            valid_generations.append(
                                PointerState(
                                    generation=gen,
                                    artifact_id=art_id,
                                    sha256=expected_digest,
                                    committed_at_utc=data.get("committed_at_utc", ""),
                                    transaction_id=data.get("transaction_id", ""),
                                    state="RECOVERED_ROLLBACK",
                                )
                            )
                except Exception:
                    continue

        if valid_generations:
            # Sort by generation descending and select highest verified generation
            valid_generations.sort(key=lambda x: x.generation, reverse=True)
            rollback_target = valid_generations[0]

            # Rewrite active pointer to rollback target
            cls.write_pointer(root_dir, rollback_target)
            old_gen = current_ptr.generation if current_ptr else "NONE"
            reason = f"ROLLED_BACK_FROM_GEN_{old_gen}_TO_GEN_{rollback_target.generation}"
            return rollback_target, reason, True

        return None, "NO_VALID_GENERATION_AVAILABLE", False


__all__ = ["ActivePointerManager"]
