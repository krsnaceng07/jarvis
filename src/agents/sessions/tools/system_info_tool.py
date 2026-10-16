"""jarvis.agents.sessions.tools.system_info_tool — System information & metrics tool.

OpenClaw parity:
Gives the agent real-time ground-truth awareness of host system time,
operating metrics, resource utilization, and running processes.
"""

from __future__ import annotations

from typing import Any, Optional

from src.system.live_clock import LiveClock
from src.system.system_metrics import SystemMetrics
from .tool_definition_wrapper import AgentTool

SYSTEM_INFO_ACTIONS = (
    "summary",
    "clock",
    "metrics",
    "processes",
)


def create_system_info_tool_definition() -> dict[str, Any]:
    return {
        "name": "system_info",
        "description": (
            "Inspect ground-truth host system information, real-time clock, resources, and processes. "
            "Supported actions: "
            "1. 'summary': Combined overview of live clock, battery, CPU, RAM, disk, and top processes. "
            "2. 'clock': Precise local time, date, day of week, UTC offset, and IANA timezone. "
            "3. 'metrics': Hardware resource telemetry (CPU %, memory %, disk %, battery %, network IPs). "
            "4. 'processes': List top active running processes sorted by memory or CPU. "
            "Always use this tool to answer questions about the current time, date, hardware usage, or PC status."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "System info action: 'summary', 'clock', 'metrics', or 'processes'.",
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Max number of processes to return (default: 8) when action is 'processes'.",
                },
            },
            "required": ["action"],
        },
    }


def create_system_info_tool(options: Optional[dict[str, Any]] = None) -> AgentTool:
    """Create runtime system_info AgentTool backed by LiveClock and SystemMetrics."""
    definition = create_system_info_tool_definition()

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: Any = None,
        on_update: Any = None,
    ) -> Any:
        action = str(params.get("action", "summary")).strip().lower()
        if not action or action not in SYSTEM_INFO_ACTIONS:
            action = "summary"

        try:
            if action == "clock":
                clock_snap = LiveClock.get_current_datetime()
                text = (
                    f"Current Host Time: {clock_snap['time_12h']}\n"
                    f"Date: {clock_snap['date']} ({clock_snap['weekday']})\n"
                    f"Timezone: {clock_snap['timezone']} (UTC{clock_snap['utc_offset']})\n"
                    f"ISO 8601: {clock_snap['datetime_iso']}"
                )
                return {
                    "content": [{"type": "text", "text": text}],
                    "data": clock_snap,
                }

            if action == "metrics":
                cpu = SystemMetrics.get_cpu_metrics()
                mem = SystemMetrics.get_memory_metrics()
                disks = SystemMetrics.get_disk_metrics()
                battery = SystemMetrics.get_battery_metrics()

                lines = [
                    f"CPU Utilization: {cpu.get('usage_percent')}% ({cpu.get('logical_cores')} logical cores)",
                    f"RAM Memory: {mem.get('usage_percent')}% used ({mem.get('used_gb')} GB / {mem.get('total_gb')} GB)",
                ]
                for drive, dinfo in disks.items():
                    lines.append(f"Disk {drive}: {dinfo.get('usage_percent')}% used ({dinfo.get('free_gb')} GB free)")
                if battery:
                    plugged = "Plugged in / Charging" if battery.get("power_plugged") else "On Battery"
                    lines.append(f"Battery: {battery.get('percent')}% ({plugged})")

                return {
                    "content": [{"type": "text", "text": "\n".join(lines)}],
                    "data": {"cpu": cpu, "memory": mem, "disks": disks, "battery": battery},
                }

            if action == "processes":
                limit = int(params.get("limit", 8))
                procs = SystemMetrics.list_running_processes(limit=limit)
                lines = [f"Top {len(procs)} Running Processes:"]
                for p in procs:
                    lines.append(
                        f"- {p['name']} (PID {p['pid']}): CPU {p['cpu_percent']}%, RAM {p['memory_percent']}%"
                    )
                return {
                    "content": [{"type": "text", "text": "\n".join(lines)}],
                    "data": {"processes": procs},
                }

            # Default: summary
            telemetry = SystemMetrics.get_full_system_telemetry()
            clock_snap = LiveClock.get_current_datetime()
            cpu = telemetry.get("cpu", {})
            mem = telemetry.get("memory", {})
            procs = telemetry.get("top_processes", [])

            lines = [
                "[HOST SYSTEM SUMMARY]",
                f"Clock: {clock_snap['time_12h']} | {clock_snap['date']} ({clock_snap['weekday']}) | TZ: {clock_snap['timezone']}",
                f"CPU: {cpu.get('usage_percent')}% | RAM: {mem.get('usage_percent')}% ({mem.get('used_gb')}/{mem.get('total_gb')} GB)",
            ]
            battery = telemetry.get("battery")
            if battery:
                plugged = "Plugged in" if battery.get("power_plugged") else "Battery"
                lines.append(f"Battery: {battery.get('percent')}% ({plugged})")

            if procs:
                proc_str = ", ".join(f"{p['name']} ({p['memory_percent']}%)" for p in procs[:4])
                lines.append(f"Active Apps: {proc_str}")

            return {
                "content": [{"type": "text", "text": "\n".join(lines)}],
                "data": {
                    "clock": clock_snap,
                    "telemetry": telemetry,
                },
            }

        except Exception as exc:
            return {
                "content": [{"type": "text", "text": f"system_info tool failed: {exc}"}]
            }

    return {
        "name": definition["name"],
        "label": "System Info",
        "description": definition["description"],
        "parameters": definition["parameters"],
        "execute": _execute,
    }


__all__ = ["create_system_info_tool", "create_system_info_tool_definition"]
