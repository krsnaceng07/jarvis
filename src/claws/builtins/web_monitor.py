"""Web Scraping & Monitor Autonomous Claw — JARVIS Autonomous Architecture (Task 4).

Periodically monitors web endpoints, scrapes remote pages or APIs, and verifies
service availability, response latency, and content integrity.
"""

from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
from typing import Any

from ..base import Claw, ClawExecutionContext
from ..types import ClawPriority, ClawResult


class WebMonitorClaw(Claw):
    """Autonomous Claw that monitors URLs, scrapes target data, and tracks uptime."""

    def __init__(
        self,
        schedule: str = "*/20 * * * *",  # Every 20 minutes
        priority: ClawPriority = ClawPriority.NORMAL,
        default_targets: list[str] | None = None,
        max_latency_ms: float = 5000.0,
    ) -> None:
        super().__init__(
            claw_id="claw:web_monitor",
            name="Web Scraping & Monitor Claw",
            description="Monitors web endpoints, scrapes target data, and tracks availability, latency, and content integrity.",
            schedule=schedule,
            priority=priority,
            timeout_seconds=45.0,
        )
        self.default_targets = default_targets or ["http://127.0.0.1:7433/health"]
        self.max_latency_ms = max_latency_ms

    async def run(self, ctx: ClawExecutionContext) -> ClawResult:
        start_time = time.monotonic()
        targets = ctx.payload.get("targets") or self.default_targets
        if isinstance(targets, str):
            targets = [targets]

        scrape_patterns = ctx.payload.get("patterns") or {}

        results: dict[str, Any] = {}
        all_ok = True
        offline_targets: list[str] = []

        for target in targets:
            url_str = str(target)
            target_start = time.monotonic()
            try:
                req = urllib.request.Request(
                    url_str,
                    headers={"User-Agent": "JARVIS-WebMonitor/1.0"},
                )
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    status_code = resp.status
                    body = resp.read()
                    target_latency = (time.monotonic() - target_start) * 1000.0

                    content_hash = hashlib.sha256(body).hexdigest()[:16]
                    text_sample = body[:500].decode("utf-8", errors="replace")

                    # Check patterns if specified
                    matched_patterns = {}
                    if url_str in scrape_patterns:
                        for pattern in scrape_patterns[url_str]:
                            matched_patterns[pattern] = pattern in text_sample

                    is_healthy = 200 <= status_code < 400 and target_latency <= self.max_latency_ms
                    if not is_healthy:
                        all_ok = False
                        offline_targets.append(url_str)

                    results[url_str] = {
                        "status_code": status_code,
                        "latency_ms": round(target_latency, 2),
                        "content_length": len(body),
                        "content_hash": content_hash,
                        "healthy": is_healthy,
                        "patterns": matched_patterns,
                    }
            except urllib.error.HTTPError as e:
                target_latency = (time.monotonic() - target_start) * 1000.0
                all_ok = False
                offline_targets.append(url_str)
                results[url_str] = {
                    "status_code": e.code,
                    "latency_ms": round(target_latency, 2),
                    "error": str(e),
                    "healthy": False,
                }
            except Exception as e:
                target_latency = (time.monotonic() - target_start) * 1000.0
                # For local loopback 127.0.0.1:7433 connection refused when gateway is down,
                # mark unhealthy but note connection status
                all_ok = False
                offline_targets.append(url_str)
                results[url_str] = {
                    "status_code": None,
                    "latency_ms": round(target_latency, 2),
                    "error": str(e),
                    "healthy": False,
                }

        duration_ms = (time.monotonic() - start_time) * 1000.0

        checkpoint_data = {
            "timestamp": time.time(),
            "targets_count": len(targets),
            "healthy": all_ok,
            "results": results,
        }
        await ctx.checkpoint(checkpoint_data)

        if not all_ok and offline_targets:
            await ctx.notify(
                "Web Monitor Alert",
                f"{len(offline_targets)} endpoint(s) degraded or offline: {', '.join(offline_targets[:3])}",
                level="warning",
            )

        summary = (
            f"Monitored {len(targets)} endpoints: "
            f"{len(targets) - len(offline_targets)} healthy, {len(offline_targets)} degraded/down."
        )

        return ClawResult(
            success=True,  # Claw run succeeded in its observation mission
            output=summary,
            duration_ms=duration_ms,
            metrics={
                "targets_count": len(targets),
                "healthy_count": len(targets) - len(offline_targets),
                "offline_count": len(offline_targets),
                "results": results,
            },
        )


__all__ = ["WebMonitorClaw"]
