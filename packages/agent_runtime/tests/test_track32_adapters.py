"""Unit tests for domain execution adapters (filesystem, process, browser, desktop, system, channels)."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile

from jarvis_agent.execution.adapters.browser import BrowserAdapter
from jarvis_agent.execution.adapters.channels import ChannelAdapter
from jarvis_agent.execution.adapters.desktop import DesktopAdapter
from jarvis_agent.execution.adapters.filesystem import FilesystemAdapter
from jarvis_agent.execution.adapters.process import ProcessAdapter
from jarvis_agent.execution.adapters.system import SystemAdapter
from jarvis_agent.orchestration.models.command import ExecutionCommand
from jarvis_agent.orchestration.models.risk import RiskAssessment, RiskClass

DUMMY_RISK = RiskAssessment(
    risk_class=RiskClass.LOW,
    blast_radius="LOCAL",
    reversibility="REVERSIBLE",
    data_sensitivity="PUBLIC",
    external_effect="NONE",
    requires_operator_approval=False,
)


def test_filesystem_adapter_atomic_write_read_delete() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        adapter = FilesystemAdapter(allowed_roots=[root])
        target_file = root / "sample.txt"

        # 1. Write file
        cmd_write = ExecutionCommand.create(
            command_id="c_w",
            task_id="t1",
            plan_id="p1",
            node_id="n1",
            execution_id="e1",
            attempt_id=1,
            plan_revision=1,
            capability_target="filesystem.write",
            arguments={"path": str(target_file), "content": "hello world", "overwrite": True},
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=DUMMY_RISK,
        )
        out_w = adapter.execute(cmd_write)
        assert out_w.success is True
        assert target_file.is_file()
        assert target_file.read_text(encoding="utf-8") == "hello world"
        assert out_w.raw_evidence["post_sha256"] == hashlib.sha256(b"hello world").hexdigest()

        # 2. Read file
        cmd_read = ExecutionCommand.create(
            command_id="c_r",
            task_id="t1",
            plan_id="p1",
            node_id="n1",
            execution_id="e1",
            attempt_id=1,
            plan_revision=1,
            capability_target="filesystem.read",
            arguments={"path": str(target_file)},
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=DUMMY_RISK,
        )
        out_r = adapter.execute(cmd_read)
        assert out_r.success is True
        assert out_r.output_data["content"] == "hello world"
        assert out_r.raw_evidence["sha256"] == hashlib.sha256(b"hello world").hexdigest()

        # 3. Path outside allowed roots rejected
        cmd_outside = ExecutionCommand.create(
            command_id="c_out",
            task_id="t1",
            plan_id="p1",
            node_id="n1",
            execution_id="e1",
            attempt_id=1,
            plan_revision=1,
            capability_target="filesystem.read",
            arguments={"path": "C:\\Windows\\System32\\calc.exe" if sys.platform == "win32" else "/etc/passwd"},
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=DUMMY_RISK,
        )
        out_out = adapter.execute(cmd_outside)
        assert out_out.success is False
        assert "outside allowed roots" in str(out_out.error_message)

        # 4. Delete file
        cmd_del = ExecutionCommand.create(
            command_id="c_d",
            task_id="t1",
            plan_id="p1",
            node_id="n1",
            execution_id="e1",
            attempt_id=1,
            plan_revision=1,
            capability_target="filesystem.delete",
            arguments={"path": str(target_file)},
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=DUMMY_RISK,
        )
        out_d = adapter.execute(cmd_del)
        assert out_d.success is True
        assert not target_file.exists()


def test_process_adapter_spawn_and_limits() -> None:
    adapter = ProcessAdapter()
    py_exec = sys.executable

    # 1. Successful spawn with stdout capture
    cmd_spawn = ExecutionCommand.create(
        command_id="c_p",
        task_id="t1",
        plan_id="p1",
        node_id="n1",
        execution_id="e_proc_1",
        attempt_id=1,
        plan_revision=1,
        capability_target="process.spawn",
        arguments={"command": py_exec, "args": ["-c", "print('hello process')"]},
        deadline_utc="2030-01-01T00:00:00Z",
        risk_assessment=DUMMY_RISK,
    )
    out = adapter.execute(cmd_spawn)
    assert out.success is True
    assert out.exit_code == 0
    assert "hello process" in out.output_data["stdout"]

    # 2. Timeout handling
    cmd_timeout = ExecutionCommand.create(
        command_id="c_to",
        task_id="t1",
        plan_id="p1",
        node_id="n1",
        execution_id="e_proc_2",
        attempt_id=1,
        plan_revision=1,
        capability_target="process.spawn",
        arguments={
            "command": py_exec,
            "args": ["-c", "import time; time.sleep(5)"],
            "timeout_seconds": 0.5,
        },
        deadline_utc="2030-01-01T00:00:00Z",
        risk_assessment=DUMMY_RISK,
    )
    out_to = adapter.execute(cmd_timeout)
    assert out_to.success is False
    assert "exceeded timeout" in str(out_to.error_message)


def test_browser_adapter_tab_reuse_and_media_control() -> None:
    adapter = BrowserAdapter()

    # 1. Open first YouTube tab
    cmd_open = ExecutionCommand.create(
        command_id="c_b1",
        task_id="t1",
        plan_id="p1",
        node_id="n1",
        execution_id="e_b1",
        attempt_id=1,
        plan_revision=1,
        capability_target="browser.open",
        arguments={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "reuse_existing": True},
        deadline_utc="2030-01-01T00:00:00Z",
        risk_assessment=DUMMY_RISK,
    )
    out1 = adapter.execute(cmd_open)
    assert out1.success is True
    assert out1.output_data["reused"] is False
    tab_id = out1.output_data["tab_id"]

    # 2. Continuation command: open/focus YouTube again -> MUST REUSE EXISTING TAB!
    cmd_reuse = ExecutionCommand.create(
        command_id="c_b2",
        task_id="t1",
        plan_id="p1",
        node_id="n2",
        execution_id="e_b2",
        attempt_id=1,
        plan_revision=1,
        capability_target="browser.open",
        arguments={"url": "https://www.youtube.com", "reuse_existing": True},
        deadline_utc="2030-01-01T00:00:00Z",
        risk_assessment=DUMMY_RISK,
    )
    out2 = adapter.execute(cmd_reuse)
    assert out2.success is True
    assert out2.output_data["reused"] is True
    assert out2.output_data["tab_id"] == tab_id

    # 3. Media control: pause playback
    cmd_pause = ExecutionCommand.create(
        command_id="c_b3",
        task_id="t1",
        plan_id="p1",
        node_id="n3",
        execution_id="e_b3",
        attempt_id=1,
        plan_revision=1,
        capability_target="browser.media_control",
        arguments={"action": "pause"},
        deadline_utc="2030-01-01T00:00:00Z",
        risk_assessment=DUMMY_RISK,
    )
    out3 = adapter.execute(cmd_pause)
    assert out3.success is True
    assert out3.output_data["action"] == "pause"
    assert out3.output_data["paused"] is True


def test_desktop_and_system_adapters() -> None:
    desk = DesktopAdapter()
    sys_ad = SystemAdapter()

    # Desktop window focus
    cmd_focus = ExecutionCommand.create(
        command_id="c_desk",
        task_id="t1",
        plan_id="p1",
        node_id="n1",
        execution_id="e_d1",
        attempt_id=1,
        plan_revision=1,
        capability_target="desktop.focus_window",
        arguments={"title": "Calculator"},
        deadline_utc="2030-01-01T00:00:00Z",
        risk_assessment=DUMMY_RISK,
    )
    out_desk = desk.execute(cmd_focus)
    assert out_desk.success is True
    assert out_desk.output_data["title"] == "Calculator"

    # System volume modification
    cmd_vol = ExecutionCommand.create(
        command_id="c_sys",
        task_id="t1",
        plan_id="p1",
        node_id="n1",
        execution_id="e_s1",
        attempt_id=1,
        plan_revision=1,
        capability_target="system.set_volume",
        arguments={"level": 0.8, "muted": False},
        deadline_utc="2030-01-01T00:00:00Z",
        risk_assessment=DUMMY_RISK,
    )
    out_sys = sys_ad.execute(cmd_vol)
    assert out_sys.success is True
    assert out_sys.output_data["level"] == 0.8


def test_channel_adapter_route_isolation_and_no_hud_leak() -> None:
    chan = ChannelAdapter(active_transports={"telegram"})

    # 1. Delivery to active Telegram channel
    cmd_tg = ExecutionCommand.create(
        command_id="c_tg",
        task_id="t1",
        plan_id="p1",
        node_id="n1",
        execution_id="e_tg",
        attempt_id=1,
        plan_revision=1,
        capability_target="channels.send_message",
        arguments={"content": "Task completed.", "channel": "telegram", "target_id": "123456"},
        deadline_utc="2030-01-01T00:00:00Z",
        risk_assessment=DUMMY_RISK,
    )
    out_tg = chan.execute(cmd_tg)
    assert out_tg.success is True
    assert out_tg.output_data["delivered"] is True
    assert len(chan.get_sent_messages()) == 1

    # 2. Inactive transport strictly fails closed and NEVER leaks to local HUD
    cmd_inactive = ExecutionCommand.create(
        command_id="c_bad_chan",
        task_id="t1",
        plan_id="p1",
        node_id="n1",
        execution_id="e_inact",
        attempt_id=1,
        plan_revision=1,
        capability_target="channels.send_message",
        arguments={"content": "Alert", "channel": "discord", "target_id": "999"},
        deadline_utc="2030-01-01T00:00:00Z",
        risk_assessment=DUMMY_RISK,
    )
    out_inactive = chan.execute(cmd_inactive)
    assert out_inactive.success is False
    assert "unavailable or unconfigured" in str(out_inactive.error_message)
    assert "Local HUD fallback forbidden" in str(out_inactive.error_message)
