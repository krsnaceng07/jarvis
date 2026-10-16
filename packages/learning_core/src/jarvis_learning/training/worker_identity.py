"""jarvis_learning.training.worker_identity — cryptographic worker identity envelope and safe orphan identification.

Guarantees:
- INV-ORPH-001: Every worker subprocess runs with a signed identity envelope.
- Safe cleanup guarantees zero collateral damage: PID reuse, similar command lines,
  and cross-supervisor processes cannot be mistakenly terminated.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Secret key used for local envelope signing
_LOCAL_ENVELOPE_SECRET = b"jarvis_learning_worker_envelope_secret_v1"


@dataclass(frozen=True, slots=True)
class WorkerIdentityEnvelope:
    """Cryptographically verifiable envelope identifying a worker child process."""

    worker_id: str
    job_id: str
    supervisor_instance_id: str
    launch_nonce: str
    creation_timestamp: float
    parent_pid: int
    process_start_time: float
    signature: str

    @classmethod
    def create(
        cls,
        supervisor_instance_id: str = "default_sup",
        job_id: str = "default_job",
        parent_pid: int | None = None,
        process_start_time: float | None = None,
        pid: int = 0,
        ppid: int | None = None,
        secret_key: str = "",
    ) -> WorkerIdentityEnvelope:
        """Construct and sign a new worker identity envelope."""
        actual_ppid = (
            ppid if ppid is not None else (parent_pid if parent_pid is not None else os.getpid())
        )
        p_pid = actual_ppid
        start_t = time.time() if process_start_time is None else process_start_time
        worker_id = f"worker_{uuid.uuid4().hex[:12]}"
        nonce = uuid.uuid4().hex

        sig = cls._compute_signature(
            worker_id=worker_id,
            job_id=job_id,
            supervisor_instance_id=supervisor_instance_id,
            launch_nonce=nonce,
            creation_timestamp=start_t,
            parent_pid=p_pid,
        )

        return cls(
            worker_id=worker_id,
            job_id=job_id,
            supervisor_instance_id=supervisor_instance_id,
            launch_nonce=nonce,
            creation_timestamp=start_t,
            parent_pid=p_pid,
            process_start_time=start_t,
            signature=sig,
        )

    @classmethod
    def _compute_signature(
        cls,
        worker_id: str,
        job_id: str,
        supervisor_instance_id: str,
        launch_nonce: str,
        creation_timestamp: float,
        parent_pid: int,
    ) -> str:
        """Compute HMAC signature over envelope fields."""
        payload = f"{worker_id}:{job_id}:{supervisor_instance_id}:{launch_nonce}:{creation_timestamp:.4f}:{parent_pid}"
        return hmac.new(_LOCAL_ENVELOPE_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify(self) -> bool:
        """Check if envelope signature is authentic."""
        expected = self._compute_signature(
            worker_id=self.worker_id,
            job_id=self.job_id,
            supervisor_instance_id=self.supervisor_instance_id,
            launch_nonce=self.launch_nonce,
            creation_timestamp=self.creation_timestamp,
            parent_pid=self.parent_pid,
        )
        return hmac.compare_digest(self.signature, expected)

    def to_token(self) -> str:
        """Serialize to compact token for CLI injection."""
        data = {
            "w_id": self.worker_id,
            "j_id": self.job_id,
            "s_id": self.supervisor_instance_id,
            "nonce": self.launch_nonce,
            "ts": self.creation_timestamp,
            "ppid": self.parent_pid,
            "sig": self.signature,
        }
        return json.dumps(data, separators=(",", ":"))

    @classmethod
    def from_token(cls, token_str: str) -> WorkerIdentityEnvelope | None:
        """Parse and verify envelope from token string."""
        try:
            data = json.loads(token_str)
            env = cls(
                worker_id=data["w_id"],
                job_id=data["j_id"],
                supervisor_instance_id=data["s_id"],
                launch_nonce=data["nonce"],
                creation_timestamp=float(data["ts"]),
                parent_pid=int(data["ppid"]),
                process_start_time=float(data["ts"]),
                signature=data["sig"],
            )
            if env.verify():
                return env
        except Exception:
            pass
        return None

    @classmethod
    def is_safe_to_reap(
        cls,
        cmdline_text: str,
        expected_supervisor_instance_id: str,
        expected_job_id: str | None = None,
        process_create_time: float | None = None,
    ) -> bool:
        """Rigorous multi-point validation before process termination."""
        # Find token in command line
        marker = "--worker-envelope="
        if marker not in cmdline_text:
            return False

        try:
            raw_token = cmdline_text.split(marker, 1)[1].split(" ", 1)[0]
            envelope = cls.from_token(raw_token)
            if not envelope:
                return False

            # Check supervisor instance ownership
            if envelope.supervisor_instance_id != expected_supervisor_instance_id:
                logger.debug(
                    "Worker envelope belongs to different supervisor '%s'; skipping",
                    envelope.supervisor_instance_id,
                )
                return False

            # Check job id if given
            if expected_job_id and envelope.job_id != expected_job_id:
                return False

            # Check PID reuse / process start time
            if process_create_time is not None:
                # Discrepancy > 10 seconds indicates PID reuse
                if abs(process_create_time - envelope.creation_timestamp) > 10.0:
                    logger.warning(
                        "PID reuse detected: creation time mismatch (env=%.1f, proc=%.1f); skipping reap",
                        envelope.creation_timestamp,
                        process_create_time,
                    )
                    return False

            return True
        except Exception as exc:
            logger.debug("Error verifying worker envelope: %s", exc)
            return False


def is_safe_to_reap(
    cmdline_text: str,
    supervisor_instance_id: str,
    expected_job_id: str | None = None,
    process_create_time: float | None = None,
    secret_key: str = "",
) -> bool:
    """Check if process command line matches an envelope belonging to supervisor_instance_id."""
    return WorkerIdentityEnvelope.is_safe_to_reap(
        cmdline_text=cmdline_text,
        expected_supervisor_instance_id=supervisor_instance_id,
        expected_job_id=expected_job_id,
        process_create_time=process_create_time,
    )
