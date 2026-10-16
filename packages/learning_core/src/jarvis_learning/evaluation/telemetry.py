"""jarvis_learning.evaluation.telemetry — Operational Metrics & Observability Collector.

Enforces:
1. INV-P9-OBS-001: Observable drop rates, queue depth, and priority classification.
2. INV-P9-OBS-002: Sampling loss disclosure and bias detection metrics.
3. Latency SLO monitoring (active_path_added_latency, local_enqueue_latency).
"""

from __future__ import annotations

import collections
import logging
import threading
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HostLatencyMetrics:
    active_turn_latency_ms: float = 0.0
    voice_input_to_response_latency_ms: float = 0.0
    active_path_added_latency_ms: float = 0.0
    local_enqueue_latency_ms: float = 0.0


@dataclass(slots=True)
class QueueObservabilityMetrics:
    queue_depth: int = 0
    total_enqueued: int = 0
    total_dropped: int = 0
    dropped_by_priority: dict[str, int] = field(default_factory=dict)
    sampling_bias_warning: bool = False
    bias_reason: str = ""


@dataclass(slots=True)
class IpcObservabilityMetrics:
    messages_sent: int = 0
    messages_received: int = 0
    stale_epoch_drops: int = 0
    duplicate_drops: int = 0
    broken_pipe_count: int = 0
    reconnect_count: int = 0
    heartbeat_age_seconds: float = 0.0


@dataclass(slots=True)
class RecoveryObservabilityMetrics:
    last_reconciliation_status: str = "CONSISTENT"
    quarantined_workers_count: int = 0
    safe_degraded_entries: int = 0
    last_action_taken: str = "NONE"


class OperationalTelemetryCollector:
    """Central singleton telemetry collector for host, queue, IPC, and recovery metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.host_latencies: collections.deque[float] = collections.deque(maxlen=1000)
        self.enqueue_latencies: collections.deque[float] = collections.deque(maxlen=1000)
        self.queue_metrics = QueueObservabilityMetrics()
        self.ipc_metrics = IpcObservabilityMetrics()
        self.recovery_metrics = RecoveryObservabilityMetrics()

    def record_host_latency(self, added_latency_ms: float, enqueue_latency_ms: float) -> None:
        with self._lock:
            self.host_latencies.append(added_latency_ms)
            self.enqueue_latencies.append(enqueue_latency_ms)

    def update_queue_metrics(
        self,
        depth: int,
        enqueued: int,
        dropped: int,
        dropped_by_priority: dict[str, int],
        bias_warning: bool,
        bias_reason: str = "",
    ) -> None:
        with self._lock:
            self.queue_metrics.queue_depth = depth
            self.queue_metrics.total_enqueued = enqueued
            self.queue_metrics.total_dropped = dropped
            self.queue_metrics.dropped_by_priority = dict(dropped_by_priority)
            self.queue_metrics.sampling_bias_warning = bias_warning
            self.queue_metrics.bias_reason = bias_reason

    def update_ipc_metrics(
        self,
        sent: int,
        received: int,
        stale_drops: int,
        dup_drops: int,
        heartbeat_age: float,
    ) -> None:
        with self._lock:
            self.ipc_metrics.messages_sent = sent
            self.ipc_metrics.messages_received = received
            self.ipc_metrics.stale_epoch_drops = stale_drops
            self.ipc_metrics.duplicate_drops = dup_drops
            self.ipc_metrics.heartbeat_age_seconds = heartbeat_age

    def update_recovery_metrics(self, status: str, action: str, quarantined: int = 0) -> None:
        with self._lock:
            self.recovery_metrics.last_reconciliation_status = status
            self.recovery_metrics.last_action_taken = action
            self.recovery_metrics.quarantined_workers_count = quarantined
            if status == "SAFE_DEGRADED":
                self.recovery_metrics.safe_degraded_entries += 1

    def get_snapshot(self) -> dict[str, Any]:
        """Return unified JSON-serializable telemetry snapshot."""
        with self._lock:
            p50_host = 0.0
            p95_host = 0.0
            p99_host = 0.0
            if self.host_latencies:
                sorted_host = sorted(self.host_latencies)
                p50_host = sorted_host[len(sorted_host) // 2]
                p95_host = sorted_host[int(len(sorted_host) * 0.95)]
                p99_host = sorted_host[int(len(sorted_host) * 0.99)]

            p50_enq = 0.0
            if self.enqueue_latencies:
                sorted_enq = sorted(self.enqueue_latencies)
                p50_enq = sorted_enq[len(sorted_enq) // 2]

            return {
                "latency_slos": {
                    "active_path_added_latency_p50_ms": round(p50_host, 3),
                    "active_path_added_latency_p95_ms": round(p95_host, 3),
                    "active_path_added_latency_p99_ms": round(p99_host, 3),
                    "local_enqueue_latency_p50_ms": round(p50_enq, 3),
                    "slo_compliant": p50_host <= 1.0 and p95_host <= 3.0 and p99_host <= 10.0,
                },
                "queue": asdict(self.queue_metrics),
                "ipc": asdict(self.ipc_metrics),
                "recovery": asdict(self.recovery_metrics),
            }


_GLOBAL_TELEMETRY: OperationalTelemetryCollector | None = None
_TEL_LOCK = threading.Lock()


def get_global_telemetry() -> OperationalTelemetryCollector:
    global _GLOBAL_TELEMETRY
    if _GLOBAL_TELEMETRY is None:
        with _TEL_LOCK:
            if _GLOBAL_TELEMETRY is None:
                _GLOBAL_TELEMETRY = OperationalTelemetryCollector()
    return _GLOBAL_TELEMETRY
