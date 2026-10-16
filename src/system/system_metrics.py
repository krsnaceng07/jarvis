"""jarvis.system.system_metrics — Live hardware, operating system, and process metrics.

Provides ground-truth real-time hardware telemetry (CPU, RAM, Disk, Battery, Network,
and running processes) using native OS interfaces (psutil / Windows APIs).
"""

from __future__ import annotations

import os
import platform
import time
from typing import Any, Dict, List, Optional
import psutil


class SystemMetrics:
    """Live system telemetry and process inspector."""

    @staticmethod
    def get_cpu_metrics() -> Dict[str, Any]:
        """Query real-time CPU utilization and architecture."""
        try:
            percent = psutil.cpu_percent(interval=0.1)
            cores_physical = psutil.cpu_count(logical=False) or 1
            cores_logical = psutil.cpu_count(logical=True) or 1
            freq = psutil.cpu_freq()
            freq_current = round(freq.current, 1) if freq else None
            return {
                "usage_percent": percent,
                "physical_cores": cores_physical,
                "logical_cores": cores_logical,
                "frequency_mhz": freq_current,
            }
        except Exception as e:
            return {"error": str(e), "usage_percent": None}

    @staticmethod
    def get_memory_metrics() -> Dict[str, Any]:
        """Query real-time RAM usage and capacity."""
        try:
            vm = psutil.virtual_memory()
            return {
                "total_gb": round(vm.total / (1024**3), 2),
                "used_gb": round(vm.used / (1024**3), 2),
                "available_gb": round(vm.available / (1024**3), 2),
                "usage_percent": vm.percent,
            }
        except Exception as e:
            return {"error": str(e), "usage_percent": None}

    @staticmethod
    def get_disk_metrics(paths: Optional[List[str]] = None) -> Dict[str, Any]:
        """Query real-time disk storage status across primary drive roots."""
        results: Dict[str, Any] = {}
        paths = paths or ["C:\\", "E:\\"] if os.name == "nt" else ["/"]
        for p in paths:
            if os.path.exists(p):
                try:
                    usage = psutil.disk_usage(p)
                    drive_name = p.rstrip("\\")
                    results[drive_name] = {
                        "total_gb": round(usage.total / (1024**3), 2),
                        "used_gb": round(usage.used / (1024**3), 2),
                        "free_gb": round(usage.free / (1024**3), 2),
                        "usage_percent": usage.percent,
                    }
                except Exception:
                    pass
        return results

    @staticmethod
    def get_battery_metrics() -> Optional[Dict[str, Any]]:
        """Query battery status if hardware sensor is available."""
        try:
            battery = psutil.sensors_battery()
            if battery:
                return {
                    "percent": battery.percent,
                    "power_plugged": battery.power_plugged,
                    "secs_left": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else None,
                }
        except Exception:
            pass
        return None

    @staticmethod
    def get_network_metrics() -> Dict[str, Any]:
        """Query network interfaces and active host connectivity."""
        interfaces: Dict[str, List[str]] = {}
        try:
            addrs = psutil.net_if_addrs()
            for name, snics in addrs.items():
                ip_list = []
                for snic in snics:
                    # AF_INET for IPv4
                    if snic.family.name in ("AF_INET", "2"):
                        ip_list.append(snic.address)
                if ip_list:
                    interfaces[name] = ip_list
        except Exception as e:
            return {"error": str(e)}
        return {"interfaces": interfaces}

    @staticmethod
    def list_running_processes(limit: int = 15) -> List[Dict[str, Any]]:
        """Query top running processes by memory/cpu footprint."""
        procs = []
        try:
            for p in psutil.process_iter(["pid", "name", "memory_percent", "cpu_percent"]):
                try:
                    info = p.info
                    name = str(info.get("name") or "")
                    # Filter out system idle or noisy low-level tasks
                    if name.lower() not in ("system idle process", "registry", "system"):
                        procs.append({
                            "pid": info["pid"],
                            "name": name,
                            "memory_percent": round(info.get("memory_percent") or 0.0, 1),
                            "cpu_percent": round(info.get("cpu_percent") or 0.0, 1),
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            # Sort by memory usage
            procs.sort(key=lambda x: x["memory_percent"], reverse=True)
            return procs[:limit]
        except Exception:
            return []

    @classmethod
    def get_full_system_telemetry(cls) -> Dict[str, Any]:
        """Return comprehensive verified host system snapshot."""
        return {
            "timestamp": time.time(),
            "os": f"{platform.system()} {platform.release()} ({platform.version()})",
            "architecture": platform.machine(),
            "cpu": cls.get_cpu_metrics(),
            "memory": cls.get_memory_metrics(),
            "disks": cls.get_disk_metrics(),
            "battery": cls.get_battery_metrics(),
            "network": cls.get_network_metrics(),
            "top_processes": cls.list_running_processes(limit=8),
            "source": "os_telemetry_apis",
            "verified": True,
        }
