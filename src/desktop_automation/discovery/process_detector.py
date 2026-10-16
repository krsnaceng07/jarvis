"""jarvis.desktop_automation.discovery.process_detector — Process discovery."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import psutil


class ProcessDetector:
    """Detects running processes, executable paths, and responsive states."""

    @staticmethod
    def list_processes() -> List[Dict[str, Any]]:
        """List all active processes with basic info."""
        results = []
        for p in psutil.process_iter(["pid", "name", "status"]):
            try:
                results.append({
                    "pid": p.pid,
                    "name": p.name(),
                    "status": p.status(),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return results

    @classmethod
    def is_process_running(cls, process_name: str) -> bool:
        """Check if any process matching process_name is running."""
        clean_name = process_name.lower().removesuffix(".exe")
        for p in cls.list_processes():
            name = p.get("name", "").lower().removesuffix(".exe")
            if name == clean_name:
                return True
        return False

    @classmethod
    def find_processes_by_name(cls, process_name: str) -> List[Dict[str, Any]]:
        """Find all running processes matching process_name."""
        clean_name = process_name.lower().removesuffix(".exe")
        matches = []
        for p in cls.list_processes():
            name = p.get("name", "").lower().removesuffix(".exe")
            if clean_name in name:
                matches.append(p)
        return matches

    @staticmethod
    def get_process_by_pid(pid: int) -> Optional[Dict[str, Any]]:
        """Retrieve details for a specific PID."""
        try:
            p = psutil.Process(pid)
            return {
                "pid": p.pid,
                "name": p.name(),
                "status": p.status(),
                "exe": p.exe() if hasattr(p, "exe") else "",
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
