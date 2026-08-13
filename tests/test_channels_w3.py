"""Wave 3 tests — HookBus lifecycle, HookAwareToolDispatcher, CronRunner, DoctorRunner."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


from src.hooks import HookBus, fire_sync
from src.hooks.lifecycle import LifecycleHooks
from src.tools.hook_dispatch import HookAwareToolDispatcher
from src.cron import CronRunner
from src.doctor import DoctorFinding, DoctorRunner, Severity


# ── HookBus ─────────────────────────────────────────────────────────────────


@dataclass
class _MockReg:
    name: str
    handler: Any
    priority: int = 0
    timeout_ms: int | None = None


class TestHookBus:
    def test_register_and_fire(self) -> None:
        bus = HookBus()
        received: list[Any] = []

        def handler(payload: Any) -> None:
            received.append(payload)

        bus.register(_MockReg(name="test_evt", handler=handler))
        fire_sync(bus, "test_evt", "hello")
        assert received == ["hello"]

    def test_fire_unknown_event_is_noop(self) -> None:
        bus = HookBus()
        fire_sync(bus, "no_such_event", None)  # must not raise

    def test_priority_order(self) -> None:
        bus = HookBus()
        order: list[int] = []
        bus.register(_MockReg(name="e", handler=lambda p: order.append(1), priority=1))
        bus.register(_MockReg(name="e", handler=lambda p: order.append(10), priority=10))
        bus.register(_MockReg(name="e", handler=lambda p: order.append(5), priority=5))
        fire_sync(bus, "e")
        assert order == [10, 5, 1]

    def test_handler_exception_does_not_stop_bus(self) -> None:
        bus = HookBus()
        called: list[int] = []
        bus.register(_MockReg(name="e", handler=lambda p: 1 / 0, priority=10))
        bus.register(_MockReg(name="e", handler=lambda p: called.append(1), priority=1))
        fire_sync(bus, "e")
        assert called == [1]

    def test_async_handler_is_awaited(self) -> None:
        bus = HookBus()
        called: list[bool] = []

        async def _async_handler(payload: Any) -> None:
            await asyncio.sleep(0)
            called.append(True)

        bus.register(_MockReg(name="e", handler=_async_handler))
        asyncio.run(bus.fire("e"))
        assert called == [True]

    def test_count_all(self) -> None:
        bus = HookBus()
        bus.register(_MockReg(name="a", handler=lambda p: None))
        bus.register(_MockReg(name="b", handler=lambda p: None))
        assert bus.count() == 2

    def test_count_named(self) -> None:
        bus = HookBus()
        bus.register(_MockReg(name="a", handler=lambda p: None))
        bus.register(_MockReg(name="a", handler=lambda p: None))
        assert bus.count("a") == 2
        assert bus.count("b") == 0

    def test_register_all(self) -> None:
        bus = HookBus()
        regs = [
            _MockReg(name="x", handler=lambda p: None),
            _MockReg(name="y", handler=lambda p: None),
        ]
        bus.register_all(regs)
        assert bus.count() == 2

    def test_names(self) -> None:
        bus = HookBus()
        bus.register(_MockReg(name="z", handler=lambda p: None))
        assert "z" in bus.names()


# ── LifecycleHooks ──────────────────────────────────────────────────────────


class TestLifecycleHooks:
    def _bus_with_collector(self) -> tuple[HookBus, list]:
        bus = HookBus()
        events: list[tuple[str, Any]] = []

        for name in (
            "session_start",
            "session_end",
            "message_received",
            "message_sent",
            "before_agent_start",
            "agent_end",
        ):
            _n = name

            def _handler(payload: Any, _name: str = _n) -> None:
                events.append((_name, payload))

            bus.register(_MockReg(name=name, handler=_handler))

        return bus, events

    def test_session_start_fires(self) -> None:
        bus, events = self._bus_with_collector()
        lh = LifecycleHooks(bus)
        lh.on_session_start({"session_id": "s1"})
        assert any(e[0] == "session_start" for e in events)

    def test_session_end_fires(self) -> None:
        bus, events = self._bus_with_collector()
        lh = LifecycleHooks(bus)
        lh.on_session_end()
        assert any(e[0] == "session_end" for e in events)

    def test_message_received_fires(self) -> None:
        bus, events = self._bus_with_collector()
        lh = LifecycleHooks(bus)
        lh.on_message_received("hello")
        assert any(e[0] == "message_received" for e in events)

    def test_message_sent_fires(self) -> None:
        bus, events = self._bus_with_collector()
        lh = LifecycleHooks(bus)
        lh.on_message_sent("bye")
        assert any(e[0] == "message_sent" for e in events)

    def test_before_agent_start_fires(self) -> None:
        bus, events = self._bus_with_collector()
        lh = LifecycleHooks(bus)
        lh.on_before_agent_start()
        assert any(e[0] == "before_agent_start" for e in events)

    def test_agent_end_fires(self) -> None:
        bus, events = self._bus_with_collector()
        lh = LifecycleHooks(bus)
        lh.on_agent_end({"kind": "success"})
        assert any(e[0] == "agent_end" for e in events)

    def test_none_bus_is_noop(self) -> None:
        lh = LifecycleHooks(None)
        lh.on_session_start()  # must not raise


# ── HookAwareToolDispatcher ─────────────────────────────────────────────────


class TestHookAwareDispatcher:
    def _make(self) -> tuple[HookAwareToolDispatcher, list, list]:
        tool_called_payloads: list[Any] = []
        tool_completed_payloads: list[Any] = []

        bus = HookBus()
        bus.register(
            _MockReg(
                name="tool_called",
                handler=lambda p: tool_called_payloads.append(p),
            )
        )
        bus.register(
            _MockReg(
                name="tool_completed",
                handler=lambda p: tool_completed_payloads.append(p),
            )
        )

        dispatcher = HookAwareToolDispatcher(
            {"ping": lambda n, a: "pong"},
            bus,
        )
        return dispatcher, tool_called_payloads, tool_completed_payloads

    def test_fires_tool_called_before(self) -> None:
        d, called, completed = self._make()
        d.execute("ping", {})
        assert len(called) == 1
        assert called[0]["tool"] == "ping"

    def test_fires_tool_completed_after(self) -> None:
        d, called, completed = self._make()
        d.execute("ping", {})
        assert len(completed) == 1
        assert completed[0]["tool"] == "ping"
        assert completed[0]["is_error"] is False

    def test_completed_hook_on_error(self) -> None:
        bus = HookBus()
        completed: list[Any] = []
        bus.register(_MockReg(name="tool_completed", handler=lambda p: completed.append(p)))
        d = HookAwareToolDispatcher({"fail": lambda n, a: 1 / 0}, bus)
        d.execute("fail", {})
        assert completed[0]["is_error"] is True

    def test_no_bus_works_normally(self) -> None:
        d = HookAwareToolDispatcher({"echo": lambda n, a: a.get("text", "")})
        res = d.execute("echo", {"text": "hi"})
        assert res.content == "hi"


# ── CronRunner ───────────────────────────────────────────────────────────────


@dataclass
class _MockJob:
    id: str
    schedule: str
    handler: Any
    enabled: bool = True


class TestCronRunner:
    def test_add_and_list(self) -> None:
        runner = CronRunner()
        job = _MockJob("j1", "* * * * *", lambda: None)
        runner.add(job)
        assert len(runner.list()) == 1

    def test_add_all(self) -> None:
        runner = CronRunner()
        jobs = [_MockJob(f"j{i}", "* * * * *", lambda: None) for i in range(3)]
        runner.add_all(jobs)
        assert len(runner.list()) == 3

    def test_remove(self) -> None:
        runner = CronRunner()
        runner.add(_MockJob("j1", "* * * * *", lambda: None))
        runner.remove("j1")
        assert len(runner.list()) == 0

    def test_start_stop(self) -> None:
        runner = CronRunner()
        runner.start(tick_seconds=60)
        assert runner._thread is not None
        runner.stop()
        assert runner._thread is None

    def test_start_idempotent(self) -> None:
        runner = CronRunner()
        runner.start(tick_seconds=60)
        t1 = runner._thread
        runner.start(tick_seconds=60)
        assert runner._thread is t1  # same thread
        runner.stop()

    def test_disabled_job_not_fired(self) -> None:
        fired: list[bool] = []
        runner = CronRunner()
        runner.add(_MockJob("j1", "* * * * *", lambda: fired.append(True), enabled=False))
        runner._tick()
        assert fired == []

    def test_always_match_fires_job(self) -> None:
        fired: list[bool] = []
        runner = CronRunner()
        runner.add(_MockJob("j1", "* * * * *", lambda: fired.append(True)))
        runner._tick()
        assert fired == [True]

    def test_job_not_fired_twice_within_30s(self) -> None:
        fired: list[bool] = []
        runner = CronRunner()
        runner.add(_MockJob("j1", "* * * * *", lambda: fired.append(True)))
        runner._tick()
        runner._tick()  # second tick within 30 s
        assert len(fired) == 1

    def test_cron_expression_mismatch_not_fired(self) -> None:
        """Job with schedule '0 0 1 1 *' (Jan 1 midnight) should not fire now."""
        fired: list[bool] = []
        runner = CronRunner()
        runner.add(_MockJob("j1", "0 0 1 1 *", lambda: fired.append(True)))
        runner._tick()
        assert fired == []


# ── DoctorRunner ─────────────────────────────────────────────────────────────


class TestDoctorRunner:
    def _ok_contract(self, plugin_id: str = "p1") -> dict:
        return {"plugin_id": plugin_id, "check": lambda: None}

    def _error_contract(self, plugin_id: str = "p2") -> dict:
        return {
            "plugin_id": plugin_id,
            "check": lambda: DoctorFinding(
                plugin_id=plugin_id,
                severity=Severity.ERROR,
                message="missing config",
            ),
        }

    def _warn_contract(self) -> dict:
        return {
            "plugin_id": "p3",
            "check": lambda: DoctorFinding(
                plugin_id="p3",
                severity=Severity.WARNING,
                message="deprecated setting",
            ),
        }

    def test_run_ok_contract(self) -> None:
        runner = DoctorRunner([self._ok_contract()])
        report = runner.run()
        assert report.is_healthy
        assert report.plugin_count == 1

    def test_run_error_contract(self) -> None:
        runner = DoctorRunner([self._error_contract()])
        report = runner.run()
        assert not report.is_healthy
        assert len(report.errors) == 1

    def test_run_warn_contract(self) -> None:
        runner = DoctorRunner([self._warn_contract()])
        report = runner.run()
        assert report.is_healthy  # warnings don't make it unhealthy
        assert len(report.warnings) == 1

    def test_run_all_three(self) -> None:
        runner = DoctorRunner([self._ok_contract(), self._error_contract(), self._warn_contract()])
        report = runner.run()
        assert not report.is_healthy
        assert len(report.errors) == 1
        assert len(report.warnings) == 1

    def test_apply_fix(self) -> None:
        fixed: list[bool] = []
        contract = {
            "plugin_id": "p1",
            "check": lambda: DoctorFinding(plugin_id="p1", severity=Severity.ERROR, message="x"),
            "fix": lambda: fixed.append(True),
        }
        runner = DoctorRunner([contract])
        report = runner.run(apply_fixes=True)
        assert fixed == [True]
        assert all(f.fix_applied for f in report.findings if f.severity == Severity.ERROR)

    def test_check_exception_becomes_error_finding(self) -> None:
        contract = {"plugin_id": "p1", "check": lambda: 1 / 0}
        runner = DoctorRunner([contract])
        report = runner.run()
        assert not report.is_healthy

    def test_invalid_contract_skipped(self) -> None:
        runner = DoctorRunner([{"plugin_id": "p1"}])  # no 'check'
        assert runner._contracts == []

    def test_disabled_contract(self) -> None:
        contract = {
            "plugin_id": "p1",
            "check": lambda: DoctorFinding(plugin_id="p1", severity=Severity.ERROR, message="x"),
            "enabled": False,
        }
        runner = DoctorRunner([contract])
        report = runner.run()
        assert report.is_healthy  # disabled → skipped → ok

    def test_summary_contains_plugin_count(self) -> None:
        runner = DoctorRunner([self._ok_contract()])
        report = runner.run()
        assert "1" in report.summary()

    def test_list_return_value_normalized(self) -> None:
        contract = {
            "plugin_id": "p1",
            "check": lambda: [
                DoctorFinding(plugin_id="p1", severity=Severity.OK, message="a"),
                DoctorFinding(plugin_id="p1", severity=Severity.WARNING, message="b"),
            ],
        }
        runner = DoctorRunner([contract])
        report = runner.run()
        assert len(report.findings) == 2
