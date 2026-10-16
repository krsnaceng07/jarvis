"""tests.test_system_metrics — Unit tests for SystemMetrics."""

from src.system.system_metrics import SystemMetrics


def test_system_metrics_cpu():
    cpu = SystemMetrics.get_cpu_metrics()
    assert isinstance(cpu, dict)
    assert cpu["physical_cores"] >= 1
    assert cpu["logical_cores"] >= 1


def test_system_metrics_memory():
    mem = SystemMetrics.get_memory_metrics()
    assert isinstance(mem, dict)
    assert mem["total_gb"] > 0
    assert 0 <= mem["usage_percent"] <= 100


def test_system_metrics_top_processes():
    procs = SystemMetrics.list_running_processes(limit=5)
    assert isinstance(procs, list)
    assert len(procs) <= 5
    if procs:
        p0 = procs[0]
        assert "pid" in p0
        assert "name" in p0
        assert "memory_percent" in p0
        assert "cpu_percent" in p0


def test_system_metrics_full_telemetry():
    telemetry = SystemMetrics.get_full_system_telemetry()
    assert isinstance(telemetry, dict)
    assert "cpu" in telemetry
    assert "memory" in telemetry
    assert "disks" in telemetry
    assert "top_processes" in telemetry
    assert telemetry["verified"] is True
