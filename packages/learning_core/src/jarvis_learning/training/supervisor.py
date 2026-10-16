"""jarvis_learning.training.supervisor — supervised child subprocess manager.

Supervises worker processes across OS boundaries, binds Windows Job Objects,
monitors heartbeats with WorkerWatchdog, and provides non-blocking IPC coordination.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .budget import TrainingBudget
from .cpu_governor import CpuGovernor
from .disk_governor import DiskGovernor
from .errors import WorkerCrashError, WorkerUnresponsiveError
from .gpu_governor import GpuGovernor
from .job_lifecycle import JobStateMachine, TrainingJobState
from .lease import SupervisorLeaseManager
from .memory_governor import MemoryGovernor, MemoryLimits
from .security_policy import SecurityPolicy
from .watchdog import WorkerWatchdog
from .worker_identity import WorkerIdentityEnvelope, is_safe_to_reap

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SupervisorOptions:
    """Configuration options for the training supervisor."""

    max_threads: int = 3
    max_memory_mb: int = 1024
    heartbeat_timeout_seconds: float = 30.0
    progress_timeout_seconds: float = 120.0
    min_free_disk_mb: float = 500.0
    security_policy: SecurityPolicy | None = None
    supervisor_instance_id: str = ""
    secret_key: str = "jarvis_training_secret"


class TrainingSupervisor:
    """Manages execution, resource containment, and watchdog supervision of a worker child."""

    def __init__(
        self,
        job_id: str,
        target: str,
        dataset_dir: Path,
        output_dir: Path,
        budget: TrainingBudget | None = None,
        options: SupervisorOptions | None = None,
        lease_manager: SupervisorLeaseManager | None = None,
    ) -> None:
        self.job_id = job_id
        self.target = target
        self.dataset_dir = Path(dataset_dir)
        self.output_dir = Path(output_dir)
        self.budget = budget or TrainingBudget()
        self.options = options or SupervisorOptions()
        self.supervisor_instance_id = (
            self.options.supervisor_instance_id or f"sup_{uuid.uuid4().hex[:8]}"
        )
        self.secret_key = self.options.secret_key or "jarvis_training_secret"
        self.lease_manager = lease_manager

        self.state_machine = JobStateMachine(job_id=job_id, current_state=TrainingJobState.DRAFT)
        self.watchdog = WorkerWatchdog(
            heartbeat_timeout_seconds=self.options.heartbeat_timeout_seconds,
            progress_timeout_seconds=self.options.progress_timeout_seconds,
        )
        self.cpu_governor = CpuGovernor(max_threads=self.options.max_threads)
        self.memory_governor = MemoryGovernor(
            limits=MemoryLimits(max_process_rss_mb=self.options.max_memory_mb)
        )
        self.gpu_governor = GpuGovernor()
        self.disk_governor = DiskGovernor(min_free_disk_mb=self.options.min_free_disk_mb)

        self.proc: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stop_requested = False
        self.ipc_messages: list[dict[str, Any]] = []

    def start(self) -> None:
        """Launch the worker child subprocess under strict resource supervision."""
        self.state_machine.transition_to(TrainingJobState.STARTING, "Supervisor launching child")

        # 0. Acquire lease if lease manager configured
        if self.lease_manager:
            self.lease_manager.acquire_lease(self.job_id, self.supervisor_instance_id)

        # 1. Disk preflight check
        self.disk_governor.check_preflight(self.output_dir)

        # 2. Build controlled environment
        env = self.cpu_governor.build_subprocess_env()
        env = self.gpu_governor.configure_environment(env)
        security = self.options.security_policy or SecurityPolicy()
        env = security.scrub_environment(env)

        # 3. Create process identity envelope
        envelope = WorkerIdentityEnvelope.create(
            supervisor_instance_id=self.supervisor_instance_id,
            secret_key=self.secret_key,
            pid=0,
            ppid=os.getpid(),
        )

        # 4. Launch subprocess
        cmd = [
            sys.executable,
            "-m",
            "jarvis_learning.training.worker",
            self.job_id,
            self.target,
            str(self.dataset_dir),
            str(self.output_dir),
            f"--worker-envelope={envelope.to_token()}",
        ]

        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

        # 5. Bind to Windows Job Object
        if self.proc.pid:
            self.memory_governor.setup_job_containment(self.proc.pid)

        # 5. Start reader thread
        self._reader_thread = threading.Thread(
            target=self._read_ipc_stream,
            daemon=True,
            name=f"TrainingSupervisorReader-{self.job_id}",
        )
        self._reader_thread.start()

    def _read_ipc_stream(self) -> None:
        """Background loop parsing JSON lines from worker stdout."""
        if not self.proc or not self.proc.stdout:
            return

        try:
            for line in self.proc.stdout:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    msg = json.loads(stripped)
                    self._handle_ipc_message(msg)
                except Exception:
                    # Non-json line, ignore or log
                    pass
        except Exception as exc:
            logger.debug("IPC stream read exception: %s", exc)

    def _handle_ipc_message(self, msg: dict[str, Any]) -> None:
        """Process incoming message from worker child."""
        self.ipc_messages.append(msg)
        msg_type = msg.get("type", "")

        match msg_type:
            case "HEARTBEAT":
                self.watchdog.record_heartbeat()
            case "PROGRESS":
                self.watchdog.record_progress()
            case "RUNNING":
                if self.state_machine.current_state == TrainingJobState.STARTING:
                    self.state_machine.transition_to(TrainingJobState.RUNNING, "Worker started")
            case "PAUSED":
                if self.state_machine.current_state == TrainingJobState.PAUSE_REQUESTED:
                    self.state_machine.transition_to(
                        TrainingJobState.PAUSED, "Worker confirmed pause"
                    )
            case "COMPLETED":
                if self.state_machine.current_state == TrainingJobState.RUNNING:
                    self.state_machine.transition_to(TrainingJobState.COMPLETED, "Worker finished")
            case "ABORTED":
                if not self.state_machine.is_terminal():
                    self.state_machine.transition_to(TrainingJobState.ABORTED, "Worker aborted")
            case "FAILED":
                if not self.state_machine.is_terminal():
                    self.state_machine.transition_to(TrainingJobState.FAILED, "Worker failed")

    def poll_and_enforce(self) -> None:
        """Periodic check called by supervisor loop to enforce watchdog and memory limits."""
        if not self.proc:
            return

        # Check process status
        exit_code = self.proc.poll()
        if exit_code is not None:
            if exit_code != 0 and not self.state_machine.is_terminal():
                self.state_machine.transition_to(
                    TrainingJobState.FAILED, f"Worker crashed with code {exit_code}"
                )
                raise WorkerCrashError(
                    f"Worker process crashed with exit code {exit_code}",
                    exit_code=exit_code,
                )
            return

        # Check watchdog liveness
        if not self.watchdog.check_liveness(raise_on_deadlock=False):
            logger.error("Watchdog detected unresponsive worker pid=%d; terminating", self.proc.pid)
            if self.state_machine.current_state in (
                TrainingJobState.RUNNING,
                TrainingJobState.PAUSE_REQUESTED,
            ):
                self.state_machine.transition_to(
                    TrainingJobState.UNRESPONSIVE, "Watchdog heartbeat timeout"
                )
            self.terminate()
            raise WorkerUnresponsiveError("Worker heartbeat timed out; process unresponsive")

        # Check memory
        if self.proc.pid:
            self.memory_governor.check_limits(self.proc.pid, raise_on_breach=True)

        # Renew supervisor lease if active
        if self.lease_manager:
            try:
                self.lease_manager.renew_lease(self.job_id, self.supervisor_instance_id)
            except Exception as exc:
                logger.error("Failed renewing job lease: %s", exc)
                self.terminate()
                raise

    def terminate(self) -> None:
        """Forcefully terminate worker process tree."""
        self.memory_governor.close()
        if self.proc:
            try:
                self.proc.kill()
                self.proc.wait(timeout=2.0)
            except Exception:
                pass
        self.gpu_governor.cleanup_cuda_context()
        if self.lease_manager:
            try:
                self.lease_manager.release_lease(self.job_id, self.supervisor_instance_id)
            except Exception:
                pass

    def wait(self, timeout_seconds: float = 60.0) -> int:
        """Wait for worker process to finish while continuously polling boundaries."""
        start = time.monotonic()
        while time.monotonic() - start < timeout_seconds:
            self.poll_and_enforce()
            if self.proc and self.proc.poll() is not None:
                return self.proc.returncode
            time.sleep(0.1)

        # Timeout reached
        logger.warning("Supervisor wait timeout exceeded (%f s)", timeout_seconds)
        self.terminate()
        return -1

    @classmethod
    def reconcile_stale_jobs(
        cls,
        jobs: list[JobStateMachine] | None = None,
        jobs_dir: Path | None = None,
    ) -> list[str]:
        """Reconcile jobs left in active non-terminal states by a dead process or host restart."""
        reconciled: list[str] = []
        if jobs:
            for sm in jobs:
                if sm.is_active():
                    sm.transition_to(
                        TrainingJobState.ABORTED,
                        reason="Supervisor restart: reconciled stale active job",
                    )
                    reconciled.append(sm.job_id)

        if jobs_dir and Path(jobs_dir).exists():
            for p in Path(jobs_dir).glob("**/job_state.json"):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    curr = data.get("current_state")
                    if curr in ("RUNNING", "STARTING", "PAUSE_REQUESTED", "CHECKPOINTING"):
                        data["current_state"] = TrainingJobState.ABORTED.value
                        data["reconciled_at"] = time.time()
                        data["reconciliation_reason"] = (
                            "Supervisor restart: reconciled stale active job"
                        )
                        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
                        reconciled.append(data.get("job_id", p.parent.name))
                except Exception as exc:
                    logger.warning("Could not reconcile job file '%s': %s", p, exc)

        return reconciled

    @classmethod
    def cleanup_orphan_workers(
        cls,
        worker_name_pattern: str = "jarvis_learning.training.worker",
        supervisor_instance_id: str = "",
        secret_key: str = "",
        enforce_identity_token: bool = False,
    ) -> int:
        """Find and terminate orphan worker child processes from previous supervisor sessions.

        When enforce_identity_token or supervisor_instance_id is provided, verifies
        the cryptographic WorkerIdentityEnvelope to ensure safe reaping without PID reuse (INV-PROC-002).
        """
        cleaned_count = 0
        try:
            import os
            import psutil

            current_pid = os.getpid()
            for proc in psutil.process_iter(["pid", "cmdline"]):
                try:
                    if proc.pid == current_pid:
                        continue
                    cmdline_list = proc.info.get("cmdline") or []
                    cmdline = " ".join(cmdline_list)
                    if worker_name_pattern in cmdline:
                        if enforce_identity_token or supervisor_instance_id:
                            if not is_safe_to_reap(
                                cmdline,
                                supervisor_instance_id=supervisor_instance_id,
                                secret_key=secret_key or "jarvis_training_secret",
                            ):
                                logger.debug(
                                    "Skipping process %d; failed identity verification",
                                    proc.pid,
                                )
                                continue
                        logger.warning(
                            "Terminating orphan training worker pid=%d: %s", proc.pid, cmdline
                        )
                        proc.kill()
                        cleaned_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception as exc:
            logger.debug("cleanup_orphan_workers exception: %s", exc)
        return cleaned_count
