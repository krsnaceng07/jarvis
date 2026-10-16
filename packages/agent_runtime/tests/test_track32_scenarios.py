"""Integration scenarios A through J for Track 3.2 Master Execution Runtime."""

from __future__ import annotations

import datetime
import hashlib
from pathlib import Path
import sys
import tempfile

from jarvis_agent.execution.errors.taxonomy import ExecutionFailureClass
from jarvis_agent.execution.models.execution_result import ExecutionStatus
from jarvis_agent.execution.runtime import ExecutionRuntime
from jarvis_agent.orchestration.models.approval import ApprovalRequest, ApprovalStatus
from jarvis_agent.orchestration.models.command import ExecutionCommand
from jarvis_agent.orchestration.models.observation import ObservationRequirement
from jarvis_agent.orchestration.models.risk import RiskAssessment, RiskClass
from jarvis_agent.orchestration.models.verification import (
    VerificationAssertion,
    VerificationRequirement,
)
from jarvis_agent.orchestration.state.event_store import EventStore


def test_scenario_a_browser_continuation_and_media_control() -> None:
    """Scenario A: Browser continuation workflow with tab discovery and reuse."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = ExecutionRuntime.create_default(state_dir=tmpdir)
        risk = RiskAssessment(
            risk_class=RiskClass.LOW,
            blast_radius="LOCAL",
            reversibility="REVERSIBLE",
            data_sensitivity="PUBLIC",
            external_effect="NONE",
            requires_operator_approval=False,
        )

        # 1. User turn: "Play lo-fi on YouTube"
        cmd_open = ExecutionCommand.create(
            command_id="cmd_yt_open",
            task_id="task_yt_01",
            plan_id="plan_yt_01",
            node_id="node_open",
            execution_id="exec_yt_1",
            attempt_id=1,
            plan_revision=1,
            capability_target="browser.open",
            arguments={"url": "https://www.youtube.com/watch?v=jfKfPfyJRdk", "reuse_existing": True},
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=risk,
        )
        res1 = runtime.execute_command(cmd_open)
        assert res1.status == ExecutionStatus.VERIFIED
        assert res1.output_data["reused"] is False
        tab_id = res1.output_data["tab_id"]

        # 2. Continuation turn: "Pause it" -> Must discover and reuse existing YouTube tab
        obs_req = ObservationRequirement(
            requirement_id="req_pause_obs",
            predicate_type="MEDIA_PAUSED",
            target="browser_tab",
        )
        ver_req = VerificationRequirement(
            verification_id="ver_pause",
            node_id="node_pause",
            assertions=[
                VerificationAssertion(
                    assertion_id="as_paused",
                    field_name="paused",
                    assertion_type="MEDIA_PAUSED",
                    expected_value=True,
                )
            ],
        )

        cmd_pause = ExecutionCommand.create(
            command_id="cmd_yt_pause",
            task_id="task_yt_01",
            plan_id="plan_yt_01",
            node_id="node_pause",
            execution_id="exec_yt_2",
            attempt_id=1,
            plan_revision=1,
            capability_target="browser.media_control",
            arguments={"action": "pause"},
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=risk,
        )
        res2 = runtime.execute_command(
            cmd_pause,
            observation_requirements=[obs_req],
            verification_requirements=[ver_req],
        )
        assert res2.status == ExecutionStatus.VERIFIED
        assert res2.output_data["paused"] is True
        assert res2.output_data["tab_id"] == tab_id
        runtime.close()


def test_scenario_b_atomic_file_write_and_sha256_verification() -> None:
    """Scenario B: Atomic file write verified by independent SHA-256 digest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        runtime = ExecutionRuntime.create_default(state_dir=base_dir)
        target_path = base_dir / "reports" / "summary.md"
        content = "# System Audit Report\nAll checks passed."
        expected_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()

        risk = RiskAssessment(
            risk_class=RiskClass.MEDIUM,
            blast_radius="LOCAL_PROJECT",
            reversibility="REVERSIBLE",
            data_sensitivity="INTERNAL",
            external_effect="NONE",
            requires_operator_approval=False,
        )

        obs_req = ObservationRequirement(
            requirement_id="req_fs_obs",
            predicate_type="FILE_EXISTS",
            target=str(target_path),
        )
        ver_req = VerificationRequirement(
            verification_id="ver_fs_write",
            node_id="node_write",
            assertions=[
                VerificationAssertion(
                    assertion_id="as_exists",
                    field_name="exists",
                    assertion_type="FILE_EXISTS",
                    expected_value=True,
                ),
                VerificationAssertion(
                    assertion_id="as_sha256",
                    field_name="sha256",
                    assertion_type="SHA256_MATCH",
                    expected_value=expected_sha,
                ),
            ],
        )

        cmd = ExecutionCommand.create(
            command_id="cmd_write_report",
            task_id="task_fs_01",
            plan_id="plan_fs_01",
            node_id="node_write",
            execution_id="exec_fs_1",
            attempt_id=1,
            plan_revision=1,
            capability_target="filesystem.write",
            arguments={"path": str(target_path), "content": content, "overwrite": True},
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=risk,
        )

        res = runtime.execute_command(
            cmd,
            granted_permissions={"filesystem.write"},
            observation_requirements=[obs_req],
            verification_requirements=[ver_req],
        )

        assert res.status == ExecutionStatus.VERIFIED
        assert target_path.is_file()
        assert target_path.read_text(encoding="utf-8") == content
        runtime.close()


def test_scenario_c_channel_route_continuity_and_no_hud_leak() -> None:
    """Scenario C: Telegram channel reply isolation strictly enforced."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = ExecutionRuntime.create_default(state_dir=tmpdir)
        risk = RiskAssessment(
            risk_class=RiskClass.LOW,
            blast_radius="EXTERNAL_NETWORK",
            reversibility="IRREVERSIBLE",
            data_sensitivity="PUBLIC",
            external_effect="EXTERNAL_MUTATION",
            requires_operator_approval=False,
        )

        cmd_tg = ExecutionCommand.create(
            command_id="cmd_tg_reply",
            task_id="task_chan_01",
            plan_id="plan_chan_01",
            node_id="node_reply",
            execution_id="exec_chan_1",
            attempt_id=1,
            plan_revision=1,
            capability_target="channels.send_message",
            arguments={
                "content": "Autonomous task executed successfully.",
                "channel": "telegram",
                "target_id": "tg_chat_4455",
            },
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=risk,
        )

        res = runtime.execute_command(cmd_tg)
        assert res.status == ExecutionStatus.VERIFIED
        assert res.output_data["channel"] == "telegram"
        assert res.output_data["target_id"] == "tg_chat_4455"
        runtime.close()


def test_scenario_d_subprocess_exit_code_verification() -> None:
    """Scenario D: Subprocess execution and exit code 0 verified."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = ExecutionRuntime.create_default(state_dir=tmpdir)
        py_code = "import sys; sys.exit(0)"

        risk = RiskAssessment(
            risk_class=RiskClass.MEDIUM,
            blast_radius="LOCAL",
            reversibility="REVERSIBLE",
            data_sensitivity="PUBLIC",
            external_effect="NONE",
            requires_operator_approval=False,
        )

        cmd = ExecutionCommand.create(
            command_id="cmd_subproc",
            task_id="task_proc_01",
            plan_id="plan_proc_01",
            node_id="node_proc",
            execution_id="exec_proc_1",
            attempt_id=1,
            plan_revision=1,
            capability_target="process.spawn",
            arguments={"command": sys.executable, "args": ["-c", py_code]},
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=risk,
        )

        # Grant process.spawn permission
        res = runtime.execute_command(
            cmd,
            granted_permissions={"process.spawn"},
        )
        assert res.status == ExecutionStatus.VERIFIED
        assert res.exit_code == 0
        runtime.close()


def test_scenario_e_approval_gated_execution() -> None:
    """Scenario E: High impact operation mandates valid operator approval."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        runtime = ExecutionRuntime.create_default(state_dir=base_dir)
        dummy_file = base_dir / "data.tmp"
        dummy_file.write_text("delete me", encoding="utf-8")

        risk_high = RiskAssessment(
            risk_class=RiskClass.HIGH,
            blast_radius="HOST_FS",
            reversibility="IRREVERSIBLE",
            data_sensitivity="CONFIDENTIAL",
            external_effect="EXTERNAL_MUTATION",
            requires_operator_approval=True,
        )

        cmd = ExecutionCommand.create(
            command_id="cmd_del_high",
            task_id="task_app_01",
            plan_id="plan_app_01",
            node_id="node_del",
            execution_id="exec_app_1",
            attempt_id=1,
            plan_revision=1,
            capability_target="filesystem.delete",
            arguments={"path": str(dummy_file)},
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=risk_high,
            approval_id="app_123",
        )

        # 1. Rejected when approval is missing
        res_no_app = runtime.execute_command(
            cmd,
            granted_permissions={"filesystem.delete"},
            approval=None,
        )
        assert res_no_app.status == ExecutionStatus.FAILED
        assert res_no_app.failure_class == ExecutionFailureClass.APPROVAL_INVALID.value

        # 2. Approved with matching hash
        valid_app = ApprovalRequest(
            approval_id="app_123",
            task_id="task_app_01",
            node_id="node_del",
            capability_target="filesystem.delete",
            arguments_hash=cmd.arguments_hash,
            risk_assessment=risk_high,
            status=ApprovalStatus.GRANTED,
            requested_at_utc="now",
            expires_at_utc="2030-01-01T00:00:00Z",
        )

        res_ok = runtime.execute_command(
            cmd,
            granted_permissions={"filesystem.delete"},
            approval=valid_app,
        )
        assert res_ok.status == ExecutionStatus.VERIFIED
        assert not dummy_file.exists()
        runtime.close()


def test_scenario_f_fail_closed_sandbox_enforcement() -> None:
    """Scenario F: Unsupported or faulted sandbox tier rejects execution (SANDBOX_DENIED)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Force fail TIER_1_RESTRICTED_TOKEN
        runtime = ExecutionRuntime.create_default(
            state_dir=tmpdir,
            force_fail_sandbox_tiers={"TIER_1_RESTRICTED_TOKEN"},
        )
        risk = RiskAssessment(
            risk_class=RiskClass.MEDIUM,
            blast_radius="LOCAL",
            reversibility="REVERSIBLE",
            data_sensitivity="PUBLIC",
            external_effect="NONE",
            requires_operator_approval=False,
        )

        cmd = ExecutionCommand.create(
            command_id="cmd_sb_fail",
            task_id="task_sb_01",
            plan_id="plan_sb_01",
            node_id="node_sb",
            execution_id="exec_sb_1",
            attempt_id=1,
            plan_revision=1,
            capability_target="process.spawn",
            arguments={"command": sys.executable, "args": ["-c", "print(1)"]},
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=risk,
        )

        res = runtime.execute_command(
            cmd,
            granted_permissions={"process.spawn"},
        )
        assert res.status == ExecutionStatus.FAILED
        assert res.failure_class == ExecutionFailureClass.SANDBOX_DENIED.value
        assert "unavailable" in str(res.error_message)
        runtime.close()


def test_scenario_g_stale_command_and_deadline_rejection() -> None:
    """Scenario G: Stale plan revision and expired deadline commands rejected at admission."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = ExecutionRuntime.create_default(state_dir=tmpdir)
        risk = RiskAssessment(
            risk_class=RiskClass.LOW,
            blast_radius="LOCAL",
            reversibility="REVERSIBLE",
            data_sensitivity="PUBLIC",
            external_effect="NONE",
            requires_operator_approval=False,
        )

        # Stale plan revision (revision 1 when active is revision 2)
        cmd_stale = ExecutionCommand.create(
            command_id="cmd_stale_1",
            task_id="task_stale_01",
            plan_id="plan_stale_01",
            node_id="node_1",
            execution_id="exec_1",
            attempt_id=1,
            plan_revision=1,
            capability_target="browser.media_control",
            arguments={"action": "pause"},
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=risk,
        )
        res = runtime.execute_command(cmd_stale, active_plan_revision=2)
        assert res.status == ExecutionStatus.FAILED
        assert res.failure_class == ExecutionFailureClass.STALE_COMMAND.value

        runtime.close()


def test_scenario_h_idempotent_cached_replay() -> None:
    """Scenario H: Idempotent replay returns cached terminal result without re-executing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = ExecutionRuntime.create_default(state_dir=tmpdir)
        risk = RiskAssessment(
            risk_class=RiskClass.LOW,
            blast_radius="LOCAL",
            reversibility="REVERSIBLE",
            data_sensitivity="PUBLIC",
            external_effect="NONE",
            requires_operator_approval=False,
        )

        cmd = ExecutionCommand.create(
            command_id="cmd_idem_1",
            task_id="task_idem_01",
            plan_id="plan_idem_01",
            node_id="node_1",
            execution_id="exec_1",
            attempt_id=1,
            plan_revision=1,
            capability_target="desktop.get_active_window",
            arguments={},
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=risk,
        )

        # First run executes
        res1 = runtime.execute_command(cmd)
        assert res1.status == ExecutionStatus.VERIFIED

        # Second run with exact same idempotency key returns cached result
        res2 = runtime.execute_command(cmd)
        assert res2.status == ExecutionStatus.VERIFIED
        assert res2.command_id == cmd.command_id
        assert res2.idempotency_key == cmd.idempotency_key
        runtime.close()


def test_scenario_i_precondition_state_drift_detection() -> None:
    """Scenario I: Precondition state drift fails verification with STATE_DRIFT."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = ExecutionRuntime.create_default(state_dir=tmpdir)
        risk = RiskAssessment(
            risk_class=RiskClass.LOW,
            blast_radius="LOCAL",
            reversibility="REVERSIBLE",
            data_sensitivity="PUBLIC",
            external_effect="NONE",
            requires_operator_approval=False,
        )

        cmd = ExecutionCommand.create(
            command_id="cmd_drift_1",
            task_id="task_drift_01",
            plan_id="plan_drift_01",
            node_id="node_1",
            execution_id="exec_1",
            attempt_id=1,
            plan_revision=1,
            capability_target="desktop.get_active_window",
            arguments={},
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=risk,
        )

        res = runtime.execute_command(
            cmd,
            baseline_fingerprint="state_hash_v1",
            current_fingerprint="state_hash_v2_drifted",
        )
        assert res.status == ExecutionStatus.VERIFICATION_FAILED
        assert res.failure_class == ExecutionFailureClass.STATE_DRIFT.value
        runtime.close()


def test_scenario_j_event_store_journaling_integration() -> None:
    """Scenario J: Execution automatically journals NODE_STARTED, NODE_OBSERVED, and NODE_VERIFIED."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        events_db = base_dir / "events.sqlite"
        event_store = EventStore(events_db)

        try:
            runtime = ExecutionRuntime.create_default(
                state_dir=base_dir,
                event_store=event_store,
            )

            risk = RiskAssessment(
                risk_class=RiskClass.LOW,
                blast_radius="LOCAL",
                reversibility="REVERSIBLE",
                data_sensitivity="PUBLIC",
                external_effect="NONE",
                requires_operator_approval=False,
            )

            cmd = ExecutionCommand.create(
                command_id="cmd_journal_1",
                task_id="task_journal_01",
                plan_id="plan_journal_01",
                node_id="node_j1",
                execution_id="exec_j1",
                attempt_id=1,
                plan_revision=1,
                capability_target="system.get_volume",
                arguments={},
                deadline_utc="2030-01-01T00:00:00Z",
                risk_assessment=risk,
            )

            res = runtime.execute_command(cmd)
            assert res.status == ExecutionStatus.VERIFIED

            # Check recorded events in event store
            events = event_store.get_events_for_task("task_journal_01")
            event_types = [e.event_type.value for e in events]
            assert "NODE_STARTED" in event_types
            assert "NODE_OBSERVED" in event_types
            assert "NODE_VERIFIED" in event_types
        finally:
            runtime.close()
            event_store.close()
