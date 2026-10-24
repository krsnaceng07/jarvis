"""Email / RSS Digest & Telemetry Autonomous Claw — JARVIS Autonomous Architecture (Task 1).

Periodically compiles execution statistics, system telemetry, and optional RSS/email feeds,
and delivers outbound summaries to Telegram, Webhooks, or desktop notifications.
"""

from __future__ import annotations

import re
import sqlite3
import time
import urllib.error
import urllib.request
from typing import Any

from ..base import Claw, ClawExecutionContext
from ..types import ClawPriority, ClawResult


class DigestClaw(Claw):
    """Autonomous Claw that compiles operational digests, parses feeds, and delivers outbound summaries."""

    def __init__(
        self,
        schedule: str = "0 9 * * *",  # Daily at 9 AM
        priority: ClawPriority = ClawPriority.LOW,
    ) -> None:
        super().__init__(
            claw_id="claw:digest_telemetry",
            name="Email / RSS Digest Claw",
            description="Compiles daily execution digests, monitors RSS/email feeds, and delivers outbound summaries.",
            schedule=schedule,
            priority=priority,
            timeout_seconds=45.0,
        )

    async def run(self, ctx: ClawExecutionContext) -> ClawResult:
        start_time = time.monotonic()
        state_dir = ctx.state_dir

        # 1. Read self-healing audit stats if available
        sh_db = state_dir / "self_healing_audit.sqlite"
        sh_events_count = 0
        if sh_db.exists():
            try:
                conn = sqlite3.connect(str(sh_db), timeout=5.0)
                cur = conn.execute("SELECT count(*) FROM recovery_audit_log;")
                sh_events_count = cur.fetchone()[0]
                conn.close()
            except Exception:
                pass

        # 2. Read claws audit stats if available
        claws_db = state_dir / "claws.sqlite"
        claw_jobs_count = 0
        failed_jobs_count = 0
        if claws_db.exists():
            try:
                conn = sqlite3.connect(str(claws_db), timeout=5.0)
                cur = conn.execute("SELECT count(*) FROM claw_jobs;")
                claw_jobs_count = cur.fetchone()[0]
                cur2 = conn.execute("SELECT count(*) FROM claw_jobs WHERE status = 'FAILED';")
                failed_jobs_count = cur2.fetchone()[0]
                conn.close()
            except Exception:
                pass

        # 3. Process optional RSS / Atom feeds if configured in payload
        rss_feeds = ctx.payload.get("rss_feeds") or []
        if isinstance(rss_feeds, str):
            rss_feeds = [rss_feeds]

        feed_items: list[dict[str, str]] = []
        for feed_url in rss_feeds:
            try:
                req = urllib.request.Request(
                    feed_url,
                    headers={"User-Agent": "JARVIS-RSS-Digest/1.0"},
                )
                with urllib.request.urlopen(req, timeout=8.0) as resp:
                    feed_xml = resp.read().decode("utf-8", errors="replace")
                    # Extract <title>...</title> tags with regex
                    titles = re.findall(r"<title>(.*?)</title>", feed_xml, flags=re.IGNORECASE)
                    for t in titles[1:6]:  # Skip channel title, take top 5 entries
                        clean_title = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t).strip()
                        if clean_title:
                            feed_items.append({"feed": feed_url, "title": clean_title})
            except Exception as e:
                feed_items.append({"feed": feed_url, "error": str(e)})

        metrics: dict[str, Any] = {
            "total_self_healing_events": sh_events_count,
            "total_claw_jobs": claw_jobs_count,
            "failed_claw_jobs": failed_jobs_count,
            "feed_items_count": len(feed_items),
        }

        digest_lines = [
            f"JARVIS System Digest: {claw_jobs_count} autonomous jobs executed, "
            f"{sh_events_count} self-healing recovery actions logged, "
            f"{failed_jobs_count} failed job(s)."
        ]
        if feed_items:
            digest_lines.append(f"Feed Updates ({len(feed_items)}):")
            for item in feed_items[:5]:
                if "title" in item:
                    digest_lines.append(f"  * {item['title']}")
                elif "error" in item:
                    digest_lines.append(f"  * [Feed Error: {item['error']}]")

        digest_summary = "\n".join(digest_lines)

        # 4. Outbound delivery to Telegram / Webhook (JARVIS Autonomous Architecture Section 8)
        outbound_info = ctx.payload.get("outbound") or {}
        webhook_url = outbound_info.get("webhook_url") or ctx.payload.get("webhook_url")
        channel = outbound_info.get("channel") or ctx.payload.get("channel", "telegram")
        recipient = outbound_info.get("recipient") or ctx.payload.get("recipient")

        outbound_res = None
        if webhook_url or recipient or ctx.payload.get("deliver_outbound"):
            outbound_res = await ctx.deliver_outbound(
                message=digest_summary,
                channel=channel,
                recipient=recipient,
                webhook_url=webhook_url,
            )
            metrics["outbound_delivery"] = outbound_res

        # 5. Checkpoint to SQLite
        await ctx.checkpoint(
            {
                "timestamp": time.time(),
                "summary": digest_summary,
                "metrics": metrics,
            }
        )

        duration_ms = (time.monotonic() - start_time) * 1000.0
        return ClawResult(
            success=True,
            output=digest_summary,
            duration_ms=duration_ms,
            metrics=metrics,
        )


__all__ = ["DigestClaw"]
