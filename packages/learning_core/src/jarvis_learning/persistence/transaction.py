"""Transaction-bound reboot identity, lifecycle, and anti-replay nonce management.

Binds every reboot validation run to an immutable transaction token, preventing
detached observations or replay of prior reboot tests.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import logging
from pathlib import Path
import time
from typing import Any
import uuid

from jarvis_learning.persistence.boot_session import BootSessionIdentity
from jarvis_learning.persistence.models import TransactionState

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class RebootTransaction:
    """Immutable record of an individual reboot validation transaction."""

    transaction_id: str
    run_id: str
    arm_id: str
    host_id: str
    pre_boot_session_id: str
    arm_timestamp_utc: str
    arm_timestamp_epoch: float
    arm_timestamp_mono_ns: int
    nonce: str
    expected_window_seconds: float
    state: TransactionState
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def is_expired(self, current_epoch: float | None = None) -> bool:
        now = time.time() if current_epoch is None else current_epoch
        return now > (self.arm_timestamp_epoch + self.expected_window_seconds)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RebootTransaction:
        return cls(
            transaction_id=data["transaction_id"],
            run_id=data["run_id"],
            arm_id=data["arm_id"],
            host_id=data["host_id"],
            pre_boot_session_id=data["pre_boot_session_id"],
            arm_timestamp_utc=data["arm_timestamp_utc"],
            arm_timestamp_epoch=float(data["arm_timestamp_epoch"]),
            arm_timestamp_mono_ns=int(data["arm_timestamp_mono_ns"]),
            nonce=data["nonce"],
            expected_window_seconds=float(data.get("expected_window_seconds", 86400.0)),
            state=TransactionState(data["state"]),
            metadata=data.get("metadata", {}),
        )


class RebootTransactionManager:
    """Manages creation, serialization, validation, and single-use nonce consumption."""

    TRANSACTION_FILE = "reboot_transaction.json"

    @classmethod
    def create_transaction(
        cls,
        pre_session: BootSessionIdentity,
        expected_window_seconds: float = 86400.0,
        metadata: dict[str, Any] | None = None,
    ) -> RebootTransaction:
        """Create a new armed reboot transaction with unique single-use cryptographic nonce."""
        tx_id = f"RBT_{uuid.uuid4().hex[:12]}"
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        arm_id = f"arm_{uuid.uuid4().hex[:8]}"
        nonce = f"nonce_{uuid.uuid4().hex}"
        now = time.time()
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        now_mono = time.monotonic_ns()

        return RebootTransaction(
            transaction_id=tx_id,
            run_id=run_id,
            arm_id=arm_id,
            host_id=pre_session.machine_guid,
            pre_boot_session_id=pre_session.boot_session_id,
            arm_timestamp_utc=now_utc,
            arm_timestamp_epoch=now,
            arm_timestamp_mono_ns=now_mono,
            nonce=nonce,
            expected_window_seconds=expected_window_seconds,
            state=TransactionState.ARMED,
            metadata=metadata or {},
        )

    @classmethod
    def save_transaction(cls, tx: RebootTransaction, lab_dir: Path) -> Path:
        """Write transaction token to lab directory."""
        lab_dir.mkdir(parents=True, exist_ok=True)
        dest = lab_dir / cls.TRANSACTION_FILE
        dest.write_text(json.dumps(tx.to_dict(), indent=2), encoding="utf-8")
        return dest

    @classmethod
    def load_transaction(cls, lab_dir: Path) -> RebootTransaction | None:
        """Load active transaction from lab directory if present."""
        path = lab_dir / cls.TRANSACTION_FILE
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return RebootTransaction.from_dict(data)
        except Exception as exc:
            logger.warning("Failed parsing transaction file: %s", exc)
            return None

    @classmethod
    def validate_for_verification(
        cls,
        tx: RebootTransaction,
        post_session: BootSessionIdentity,
    ) -> tuple[bool, str]:
        """Validate that transaction is eligible for post-reboot verification."""
        if tx.state != TransactionState.ARMED:
            return False, f"Invalid transaction state: {tx.state.value} (expected ARMED)"

        if tx.is_expired():
            return (
                False,
                f"Transaction {tx.transaction_id} expired (window: {tx.expected_window_seconds}s)",
            )

        if tx.host_id != post_session.machine_guid:
            return False, f"Host ID mismatch: {tx.host_id} != {post_session.machine_guid}"

        return True, "Transaction is valid and eligible for verification"

    @classmethod
    def transition_state(
        cls,
        tx: RebootTransaction,
        new_state: TransactionState,
        lab_dir: Path,
    ) -> RebootTransaction:
        """Transition transaction state and consume anti-replay nonce."""
        updated = RebootTransaction(
            transaction_id=tx.transaction_id,
            run_id=tx.run_id,
            arm_id=tx.arm_id,
            host_id=tx.host_id,
            pre_boot_session_id=tx.pre_boot_session_id,
            arm_timestamp_utc=tx.arm_timestamp_utc,
            arm_timestamp_epoch=tx.arm_timestamp_epoch,
            arm_timestamp_mono_ns=tx.arm_timestamp_mono_ns,
            nonce=f"CONSUMED_{tx.nonce[:8]}",  # Invalidate nonce
            expected_window_seconds=tx.expected_window_seconds,
            state=new_state,
            metadata=dict(tx.metadata),
        )
        cls.save_transaction(updated, lab_dir)
        return updated


__all__ = ["RebootTransaction", "RebootTransactionManager"]
