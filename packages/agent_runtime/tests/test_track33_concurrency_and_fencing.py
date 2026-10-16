"""Track 3.3 Concurrency, Resource Arbitration, and Worker Fencing Test Suite (S25–S34).

Validates:
S25: Desktop input exclusive mutual exclusion between concurrent tasks.
S26: Fine-grained browser tab targeting allowing different tabs/domains to run concurrently.
S27: Filesystem path write exclusivity blocking conflicting writes to the same directory/file.
S28: Concurrent filesystem read sharing without blocking.
S29: Atomic multi-resource acquisition with rollback on partial contention.
S30: Deterministic deadlock prevention via alphabetical composite key ordering.
S31: Monotonic fencing generation increments on re-acquisition.
S32: Stale worker operation rejection when presented fencing generation is superseded.
S33: Worker registration, active heartbeats, and status transitions.
S34: Stale worker heartbeat timeout detection and automatic fencing.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from jarvis_agent.scheduling.arbitration.resource_arbitrator import ResourceArbitrator
from jarvis_agent.scheduling.models.resource import (
    ResourceClaim,
    ResourceClass,
    ResourceMode,
)
from jarvis_agent.scheduling.models.worker import WorkerStatus
from jarvis_agent.scheduling.storage.projection_store import ProjectionStore
from jarvis_agent.scheduling.worker.worker_manager import WorkerManager


def test_s25_desktop_input_mutual_exclusion():
    """S25: Desktop input exclusive mutual exclusion between concurrent tasks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectionStore(Path(tmpdir) / "test_arb.sqlite")
        arbitrator = ResourceArbitrator(store)
        try:
            claim_taskA = ResourceClaim(
                "c1",
                "taskA",
                "node1",
                ResourceClass.DESKTOP_INPUT,
                "primary_screen",
                ResourceMode.EXCLUSIVE,
            )
            claim_taskB = ResourceClaim(
                "c2",
                "taskB",
                "node2",
                ResourceClass.DESKTOP_INPUT,
                "primary_screen",
                ResourceMode.EXCLUSIVE,
            )

            resA = arbitrator.acquire_resources([claim_taskA], "workerA")
            assert resA.granted

            # taskB tries to acquire desktop input -> blocked
            resB = arbitrator.acquire_resources([claim_taskB], "workerB")
            assert not resB.granted
            assert "DESKTOP_INPUT:primary_screen" in resB.blocked_by_key
        finally:
            store.close()


def test_s26_fine_grained_browser_tabs_concurrency():
    """S26: Fine-grained browser tab targeting allows different tabs to run concurrently."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectionStore(Path(tmpdir) / "test_arb.sqlite")
        arbitrator = ResourceArbitrator(store)
        try:
            claim_tab1 = ResourceClaim(
                "c1",
                "taskA",
                "node1",
                ResourceClass.BROWSER_TAB,
                "youtube.com:tab_1",
                ResourceMode.EXCLUSIVE,
            )
            claim_tab2 = ResourceClaim(
                "c2",
                "taskB",
                "node2",
                ResourceClass.BROWSER_TAB,
                "github.com:tab_2",
                ResourceMode.EXCLUSIVE,
            )

            res1 = arbitrator.acquire_resources([claim_tab1], "workerA")
            res2 = arbitrator.acquire_resources([claim_tab2], "workerB")

            # Both should be granted since they target different browser tabs
            assert res1.granted
            assert res2.granted
        finally:
            store.close()


def test_s27_filesystem_path_write_exclusivity():
    """S27: Filesystem path write exclusivity blocks conflicting writes to same target."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectionStore(Path(tmpdir) / "test_arb.sqlite")
        arbitrator = ResourceArbitrator(store)
        try:
            claim_writeA = ResourceClaim(
                "c1",
                "taskA",
                "node1",
                ResourceClass.FILESYSTEM_PATH,
                "C:/data/config.json",
                ResourceMode.EXCLUSIVE,
            )
            claim_writeB = ResourceClaim(
                "c2",
                "taskB",
                "node2",
                ResourceClass.FILESYSTEM_PATH,
                "C:/data/config.json",
                ResourceMode.EXCLUSIVE,
            )

            resA = arbitrator.acquire_resources([claim_writeA], "workerA")
            assert resA.granted

            resB = arbitrator.acquire_resources([claim_writeB], "workerB")
            assert not resB.granted
        finally:
            store.close()


def test_s28_concurrent_filesystem_read_sharing():
    """S28: Concurrent filesystem read sharing without blocking."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectionStore(Path(tmpdir) / "test_arb.sqlite")
        arbitrator = ResourceArbitrator(store)
        try:
            claim_readA = ResourceClaim(
                "c1",
                "taskA",
                "node1",
                ResourceClass.FILESYSTEM_READ,
                "C:/data/source.txt",
                ResourceMode.SHARED,
            )
            claim_readB = ResourceClaim(
                "c2",
                "taskB",
                "node2",
                ResourceClass.FILESYSTEM_READ,
                "C:/data/source.txt",
                ResourceMode.SHARED,
            )

            resA = arbitrator.acquire_resources([claim_readA], "workerA")
            resB = arbitrator.acquire_resources([claim_readB], "workerB")

            assert resA.granted
            assert resB.granted
        finally:
            store.close()


def test_s29_atomic_multi_resource_rollback():
    """S29: Atomic multi-resource acquisition with rollback on partial contention."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectionStore(Path(tmpdir) / "test_arb.sqlite")
        arbitrator = ResourceArbitrator(store)
        try:
            # Worker 1 holds resource R2
            claim_r2_held = ResourceClaim(
                "c_r2",
                "task0",
                "node0",
                ResourceClass.FILESYSTEM_PATH,
                "R2",
                ResourceMode.EXCLUSIVE,
            )
            res_hold = arbitrator.acquire_resources([claim_r2_held], "worker1")
            assert res_hold.granted

            # Worker 2 tries to acquire R1 and R2
            claim_r1 = ResourceClaim(
                "c_r1",
                "task1",
                "node1",
                ResourceClass.FILESYSTEM_PATH,
                "R1",
                ResourceMode.EXCLUSIVE,
            )
            claim_r2 = ResourceClaim(
                "c_r2_b",
                "task1",
                "node1",
                ResourceClass.FILESYSTEM_PATH,
                "R2",
                ResourceMode.EXCLUSIVE,
            )

            res_w2 = arbitrator.acquire_resources([claim_r1, claim_r2], "worker2")
            # Should fail because R2 is locked
            assert not res_w2.granted

            # Invariant: R1 must have been rolled back and not left orphaned/locked
            res_check_r1 = arbitrator.acquire_resources([claim_r1], "worker3")
            assert res_check_r1.granted
        finally:
            store.close()


def test_s30_deadlock_prevention_ordering():
    """S30: Deterministic deadlock prevention via alphabetical composite key ordering."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectionStore(Path(tmpdir) / "test_arb.sqlite")
        arbitrator = ResourceArbitrator(store)
        try:
            claim_z = ResourceClaim(
                "cz", "t1", "n1", ResourceClass.FILESYSTEM_PATH, "Z_FILE", ResourceMode.EXCLUSIVE
            )
            claim_a = ResourceClaim(
                "ca", "t1", "n1", ResourceClass.FILESYSTEM_PATH, "A_FILE", ResourceMode.EXCLUSIVE
            )

            res = arbitrator.acquire_resources([claim_z, claim_a], "workerA")
            assert res.granted
            assert len(res.leases) == 2
            # Leases should have been acquired in alphabetical order: A_FILE before Z_FILE
            assert res.leases[0].claim.target_key == "A_FILE"
            assert res.leases[1].claim.target_key == "Z_FILE"
        finally:
            store.close()


def test_s31_monotonic_fencing_generation():
    """S31: Monotonic fencing generation increments on re-acquisition."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectionStore(Path(tmpdir) / "test_arb.sqlite")
        arbitrator = ResourceArbitrator(store)
        try:
            claim = ResourceClaim(
                "c1", "t1", "n1", ResourceClass.BROWSER_TAB, "tab_10", ResourceMode.EXCLUSIVE
            )
            res1 = arbitrator.acquire_resources([claim], "workerA")
            assert res1.leases[0].fencing_token.generation == 1

            res2 = arbitrator.acquire_resources([claim], "workerA")
            assert res2.leases[0].fencing_token.generation == 2
        finally:
            store.close()


def test_s32_stale_worker_operation_rejection():
    """S32: Stale worker operation rejection when presented generation is superseded."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectionStore(Path(tmpdir) / "test_arb.sqlite")
        worker_mgr = WorkerManager(store)
        arbitrator = ResourceArbitrator(store)
        try:
            claim = ResourceClaim(
                "c1", "t1", "n1", ResourceClass.DESKTOP_INPUT, "screen", ResourceMode.EXCLUSIVE
            )
            res1 = arbitrator.acquire_resources([claim], "workerA")
            gen1 = res1.leases[0].fencing_token.generation

            # Worker B supersedes with generation 2
            # First expire workerA lease to allow acquisition
            arbitrator.release_resources(res1.leases)
            res2 = arbitrator.acquire_resources([claim], "workerB")
            gen2 = res2.leases[0].fencing_token.generation
            assert gen2 > gen1

            # Validate generation: gen1 must be rejected, gen2 accepted
            assert not worker_mgr.validate_fencing_generation(claim.composite_key, gen1)
            assert worker_mgr.validate_fencing_generation(claim.composite_key, gen2)
        finally:
            store.close()


def test_s33_worker_registration_and_heartbeat():
    """S33: Worker registration, active heartbeats, and status transitions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectionStore(Path(tmpdir) / "test_arb.sqlite")
        worker_mgr = WorkerManager(store)
        try:
            worker = worker_mgr.register_worker(worker_epoch=1, heartbeat_timeout_seconds=10.0)
            assert worker.status == WorkerStatus.ACTIVE
            assert worker.worker_id.startswith("worker_")

            # Heartbeat update
            hb_ok = worker_mgr.heartbeat(worker.worker_id)
            assert hb_ok
        finally:
            store.close()


def test_s34_stale_worker_timeout_and_fencing():
    """S34: Stale worker heartbeat timeout detection and automatic fencing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectionStore(Path(tmpdir) / "test_arb.sqlite")
        worker_mgr = WorkerManager(store)
        try:
            # Register worker with 0.0 second timeout to immediately simulate timeout
            worker = worker_mgr.register_worker(worker_epoch=1, heartbeat_timeout_seconds=0.0)
            fenced = worker_mgr.fence_stale_workers()
            assert worker.worker_id in fenced

            # Heartbeat on fenced worker must fail
            hb_ok = worker_mgr.heartbeat(worker.worker_id)
            assert not hb_ok
        finally:
            store.close()
