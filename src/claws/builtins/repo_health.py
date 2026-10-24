"""Repository Health & Lint Autonomous Claw — JARVIS Autonomous Architecture (Task 3).

Periodically audits repository status, branch tracking, uncommitted files,
and automated code hygiene / lint status.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Any

from ..base import Claw, ClawExecutionContext
from ..types import ClawPriority, ClawResult


class RepositoryHealthClaw(Claw):
    """Autonomous Claw that monitors repository state, git status, and code hygiene/lint."""

    def __init__(
        self,
        schedule: str = "*/30 * * * *",  # Every 30 minutes
        priority: ClawPriority = ClawPriority.NORMAL,
        max_uncommitted_warning: int = 25,
    ) -> None:
        super().__init__(
            claw_id="claw:repository_health",
            name="Repository Health & Lint Claw",
            description="Audits git status, uncommitted changes, code hygiene, and lint status.",
            schedule=schedule,
            priority=priority,
            timeout_seconds=45.0,
        )
        self.max_uncommitted_warning = max_uncommitted_warning

    async def run(self, ctx: ClawExecutionContext) -> ClawResult:
        start_time = time.monotonic()
        ws_root = ctx.workspace_root

        metrics: dict[str, Any] = {}
        try:
            # 1. Check current branch
            branch_proc = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(ws_root),
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else "unknown"

            # 2. Check git status
            status_proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(ws_root),
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            changes = [line.strip() for line in status_proc.stdout.splitlines() if line.strip()]
            modified_count = len(changes)

            metrics["branch"] = branch
            metrics["uncommitted_changes_count"] = modified_count
            metrics["is_clean"] = modified_count == 0

            # 3. Code Hygiene & Lint check
            lint_errors_count = 0
            lint_checked = False
            lint_tool = "none"

            # Check if ruff is available
            ruff_bin = shutil.which("ruff")
            uv_bin = shutil.which("uv")
            if uv_bin or ruff_bin:
                try:
                    cmd = (
                        [uv_bin, "run", "ruff", "check", "--output-format", "json", "src/claws"]
                        if uv_bin
                        else [ruff_bin, "check", "--output-format", "json", "src/claws"]
                    )
                    lint_proc = subprocess.run(
                        cmd,
                        cwd=str(ws_root),
                        capture_output=True,
                        text=True,
                        timeout=15.0,
                    )
                    lint_checked = True
                    lint_tool = "ruff"
                    if lint_proc.stdout.strip():
                        try:
                            lint_data = json.loads(lint_proc.stdout)
                            lint_errors_count = len(lint_data)
                        except Exception:
                            lint_errors_count = 0 if lint_proc.returncode == 0 else 1
                    else:
                        lint_errors_count = 0 if lint_proc.returncode == 0 else 1
                except Exception:
                    lint_checked = False

            metrics["lint_checked"] = lint_checked
            metrics["lint_tool"] = lint_tool
            metrics["lint_errors_count"] = lint_errors_count

            is_healthy = lint_errors_count == 0

            if modified_count >= self.max_uncommitted_warning:
                await ctx.notify(
                    "Repository Hygiene Warning",
                    f"Repository has {modified_count} uncommitted files on branch '{branch}'.",
                    level="warning",
                )

            if lint_errors_count > 0:
                await ctx.notify(
                    "Repository Lint Alert",
                    f"Found {lint_errors_count} code hygiene / lint issue(s).",
                    level="warning",
                )

            await ctx.checkpoint(
                {
                    "timestamp": time.time(),
                    "branch": branch,
                    "uncommitted_count": modified_count,
                    "lint_errors": lint_errors_count,
                    "healthy": is_healthy,
                }
            )

            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ClawResult(
                success=True,
                output=(
                    f"Repo branch: {branch}, uncommitted changes: {modified_count}, "
                    f"lint errors: {lint_errors_count} (tool: {lint_tool})"
                ),
                duration_ms=duration_ms,
                metrics=metrics,
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ClawResult(
                success=False,
                error=f"Failed to inspect repository health: {e}",
                duration_ms=duration_ms,
                metrics={"error": str(e)},
            )


__all__ = ["RepositoryHealthClaw"]
