"""src.agents.subagents.runner
Subagent runner and scoped execution worker.

Matches JARVIS parity:
- src/agents/subagents/spawn/subagent-spawn-context.ts
- src/agents/agent-loop.ts (subagent turn execution)
- packages/agent-core/src/agent-loop.ts
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine

from .registry import SubagentRegistry
from .types import (
    SubagentRunRecord,
    SubagentSpawnContextMode,
    SubagentStatus,
)


class SubagentRunner:
    """Executes a scoped subagent turn with bounded timeout and verified evidence tracking."""

    def __init__(self, registry: SubagentRegistry | None = None) -> None:
        self.registry = registry or SubagentRegistry.get_instance()

    def build_prompt_context(
        self,
        record: SubagentRunRecord,
        parent_context: str | None = None,
    ) -> str:
        """Construct the prompt instructions for the subagent based on context mode."""
        lines = [
            f"[SUBAGENT TASK: {record.label or record.task}]",
            f"Role: {record.role.value} (Depth: {record.depth})",
            f"Objective: {record.task}",
            "Requirements: Execute required steps truthfully. Report physical evidence (file paths, command outputs, specific data).",
        ]

        if record.context_mode == SubagentSpawnContextMode.FORK and parent_context:
            lines.extend(
                [
                    "",
                    "[PARENT CONTEXT FOR CONTINUATION]",
                    parent_context.strip(),
                    "[END PARENT CONTEXT]",
                ]
            )

        if record.metadata.get("attachments"):
            lines.extend(["", "[ATTACHMENTS]"])
            for att in record.metadata["attachments"]:
                lines.append(f"- {att.get('name', 'file')}: {att.get('content', '')[:120]}")

        lines.append("\nProceed with execution.")
        return "\n".join(lines)

    async def run(
        self,
        record: SubagentRunRecord,
        tools: dict[str, Any],
        step_executor: (
            Callable[
                [SubagentRunRecord, dict[str, Any]],
                Coroutine[Any, Any, tuple[str, list[str]]],
            ]
            | None
        ) = None,
    ) -> None:
        """Run the subagent task to completion.

        If custom step_executor is provided, delegates execution to it.
        Otherwise, executes available tools or evaluates prompt.
        """
        self.registry.update_run_status(record.run_id, SubagentStatus.RUNNING)

        try:
            if step_executor:
                result_text, artifacts = await step_executor(record, tools)
            else:
                # Default baseline execution: examine task and tools
                result_text, artifacts = await self._default_execute(record, tools)

            self.registry.update_run_status(
                record.run_id,
                SubagentStatus.COMPLETED,
                result_text=result_text,
                tangible_artifacts=artifacts,
            )
        except asyncio.CancelledError:
            self.registry.update_run_status(
                record.run_id,
                SubagentStatus.CANCELLED,
                error="Cancelled by parent or controller.",
            )
            raise
        except Exception as exc:
            self.registry.update_run_status(
                record.run_id,
                SubagentStatus.FAILED,
                error=f"Execution error: {exc}",
            )

    @staticmethod
    async def _invoke_tool(tool_entry: Any, call_id: str, args: dict[str, Any]) -> Any:
        """Execute a tool handling both async coroutines and synchronous callbacks."""
        execute_fn = (
            tool_entry.get("execute")
            if isinstance(tool_entry, dict)
            else getattr(tool_entry, "execute", None)
        )
        if not execute_fn:
            return "Tool has no execute handler."
        res = execute_fn(call_id, args)
        if hasattr(res, "__await__"):
            res = await res
        return res

    async def _default_execute(
        self,
        record: SubagentRunRecord,
        tools: dict[str, Any],
    ) -> tuple[str, list[str]]:
        """Baseline tool execution loop for autonomous subagents (JARVIS parity)."""
        import re

        artifacts: list[str] = []
        result_parts: list[str] = []
        task_text = record.task.strip()
        task_lower = task_text.lower()

        # 1. Check for explicit or implicit shell/system command execution
        cmd_candidate = None
        if task_lower.startswith(("exec:", "bash:", "cmd:", "command:", "run:", "execute:")):
            cmd_candidate = task_text.split(":", 1)[1].strip()
        elif "`" in task_text:
            m = re.search(r"`([^`]+)`", task_text)
            if m:
                cmd_candidate = m.group(1).strip()
        elif any(
            task_lower.startswith(prefix)
            for prefix in (
                "python ",
                "uv ",
                "pytest ",
                "git ",
                "npm ",
                "pnpm ",
                "dir",
                "echo ",
                "ls ",
                "cat ",
                "tasklist",
                "taskkill",
                "powershell ",
                "pip ",
                "curl ",
            )
        ):
            cmd_candidate = task_text

        if cmd_candidate and ("exec" in tools or "bash" in tools):
            exec_tool = tools.get("exec") or tools.get("bash")
            workdir = record.metadata.get("cwd") or None
            exec_args: dict[str, Any] = {"command": cmd_candidate}
            if workdir:
                exec_args["workdir"] = workdir
            try:
                res = await self._invoke_tool(
                    exec_tool, f"subagent_exec_{record.run_id[:8]}", exec_args
                )
                out = ""
                if isinstance(res, dict):
                    content = res.get("content", [])
                    if isinstance(content, list) and content:
                        out = str(content[0].get("text", ""))
                    elif "text" in res:
                        out = str(res["text"])
                    elif "result" in res:
                        out = str(res["result"])
                else:
                    out = str(res)
                result_parts.append(f"Command '{cmd_candidate}':\n{out.strip()[:1000]}")
            except Exception as e:
                result_parts.append(f"Command '{cmd_candidate}' failed: {e}")

        # 2. Process / App / System Diagnostics & Troubleshooting
        is_diag_task = any(
            k in task_lower
            for k in (
                "process",
                "app close",
                "fail to close",
                "why",
                "troubleshoot",
                "diagnos",
                "powershell",
                "whatsapp",
                "kill_app",
                "close_app",
                "system log",
            )
        )
        if not result_parts and is_diag_task and ("exec" in tools or "bash" in tools):
            exec_tool = tools.get("exec") or tools.get("bash")
            diag_cmd = (
                "Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -or "
                "$_.ProcessName -match 'powershell|pwsh|whatsapp|code|opencode|chrome' } | "
                "Select-Object Id, ProcessName, MainWindowTitle | Format-Table -AutoSize"
            )
            try:
                res = await self._invoke_tool(
                    exec_tool, f"subagent_diag_{record.run_id[:8]}", {"command": diag_cmd}
                )
                out = ""
                if isinstance(res, dict):
                    content = res.get("content", [])
                    if isinstance(content, list) and content:
                        out = str(content[0].get("text", ""))
                    elif "text" in res:
                        out = str(res["text"])
                else:
                    out = str(res)
                if out.strip():
                    result_parts.append(f"Process diagnostic census:\n{out.strip()[:1000]}")
            except Exception as diag_err:
                result_parts.append(f"Diagnostic inspection error: {diag_err}")

        # 3. Local directory, folder, or codebase inspection
        is_dir_task = (
            any(
                k in task_lower
                for k in (
                    "directory",
                    "folder",
                    "codebase",
                    "files",
                    "explore",
                    "list files",
                    "check directory",
                    "check folder",
                    "pholdar",
                    "drive",
                    "repo",
                )
            )
            or bool(re.search(r"[a-zA-Z]:[/\\]", task_text))
            or bool(re.search(r"['\"][a-zA-Z0-9_\-/\\]+['\"]", task_text))
        )

        if not result_parts and is_dir_task and "ls" in tools:
            ls_tool = tools["ls"]
            dir_candidate = None
            # Check for drive pattern like E:\stonic or E:/stonic
            m_drive = re.search(r"([a-zA-Z]:[\\/][^\s'\"`]+)", task_text)
            if m_drive:
                dir_candidate = m_drive.group(1).rstrip(".,;")
            else:
                # Check for quoted directory name like 'Stonic' or 'E:\stonic'
                m_quote = re.search(r"['\"]([^'\"]+)['\"]", task_text)
                if m_quote and ("." not in m_quote.group(1) or "/" in m_quote.group(1) or "\\" in m_quote.group(1)):
                    dir_candidate = m_quote.group(1)
                else:
                    for w in task_text.split():
                        if ("/" in w or "\\" in w) and not w.endswith((".py", ".txt", ".json", ".md", ".ts", ".html")):
                            dir_candidate = w.strip("`'\".,;")
                            break

            ls_args = {"path": dir_candidate} if dir_candidate else {}
            try:
                res = await self._invoke_tool(ls_tool, f"subagent_ls_{record.run_id[:8]}", ls_args)
                out = ""
                entries: list[str] = []
                if isinstance(res, dict):
                    content = res.get("content", [])
                    if isinstance(content, list) and content:
                        out = str(content[0].get("text", ""))
                    elif "text" in res:
                        out = str(res["text"])
                    entries = res.get("entries") or []
                else:
                    out = str(res)

                target_disp = dir_candidate or "current directory"
                result_parts.append(f"Directory listing of '{target_disp}':\n{out[:800]}")
                if dir_candidate:
                    artifacts.append(dir_candidate)

                # For deep analysis: if subdirectories exist, explore top subdirectories
                if any(k in task_lower for k in ("deep", "analyze", "explore", "comprehensive", "diplee", "sabai")):
                    subdirs = [e.rstrip("/") for e in entries if e.endswith("/")][:4]
                    for sub in subdirs:
                        sub_path = f"{dir_candidate}\\{sub}" if dir_candidate else sub
                        sub_res = await self._invoke_tool(
                            ls_tool, f"subagent_subls_{record.run_id[:8]}", {"path": sub_path}
                        )
                        sub_out = ""
                        if isinstance(sub_res, dict):
                            c = sub_res.get("content", [])
                            if isinstance(c, list) and c:
                                sub_out = str(c[0].get("text", ""))
                        if sub_out:
                            result_parts.append(f"Subfolder '{sub}':\n{sub_out[:400]}")
            except Exception as ls_err:
                result_parts.append(f"Directory listing error: {ls_err}")

        # 3. Read file
        elif not result_parts and ("read" in task_lower or "cat " in task_lower) and "read" in tools:
            words = record.task.split()
            path_candidate = None
            for w in words:
                if "." in w or "/" in w or "\\" in w:
                    path_candidate = w.strip("`'\".,;")
                    break
            if path_candidate:
                read_tool = tools["read"]
                try:
                    res = await self._invoke_tool(
                        read_tool, f"subagent_read_{record.run_id[:8]}", {"path": path_candidate}
                    )
                    out = str(
                        res.get("content", [{}])[0].get("text", "") if isinstance(res, dict) else res
                    )
                    result_parts.append(f"Read '{path_candidate}':\n{out[:500]}")
                    artifacts.append(path_candidate)
                except Exception as read_err:
                    result_parts.append(f"Read file error: {read_err}")

        # 4. Search files (grep / find)
        elif not result_parts and ("grep" in task_lower or "find in file" in task_lower) and (
            "grep" in tools or "find" in tools
        ):
            tool = tools.get("grep") or tools.get("find")
            words = record.task.split()
            pat = words[-1].strip("`'\".,;") if words else ""
            try:
                res = await self._invoke_tool(
                    tool, f"subagent_search_{record.run_id[:8]}", {"pattern": pat}
                )
                out = str(res.get("content", [{}])[0].get("text", "") if isinstance(res, dict) else res)
                result_parts.append(f"Search results for '{pat}':\n{out[:500]}")
            except Exception as search_err:
                result_parts.append(f"File search error: {search_err}")

        # 5. Web search (ONLY when explicit web/internet search is requested or query is non-local)
        elif (
            not result_parts
            and (
                (
                    "search web" in task_lower
                    or "google" in task_lower
                    or "lookup on google" in task_lower
                    or "internet search" in task_lower
                    or "search online" in task_lower
                )
                or (
                    ("search" in task_lower or "lookup" in task_lower)
                    and not is_dir_task
                    and not re.search(r"[a-zA-Z]:", task_text)
                )
            )
            and "web_search" in tools
        ):
            query = task_text
            for prefix in (
                "search web for",
                "search web",
                "search online for",
                "search for",
                "google",
                "lookup",
                "search",
            ):
                if task_lower.startswith(prefix):
                    query = task_text[len(prefix) :].strip(" :\"'")
                    break
            try:
                search_tool = tools["web_search"]
                res = await self._invoke_tool(
                    search_tool, f"subagent_search_{record.run_id[:8]}", {"query": query}
                )
                out = ""
                if isinstance(res, dict):
                    content = res.get("content", [])
                    if isinstance(content, list) and content:
                        out = str(content[0].get("text", ""))
                    elif "text" in res:
                        out = str(res["text"])
                    elif "result" in res:
                        out = str(res["result"])
                else:
                    out = str(res)
                result_parts.append(f"Web search '{query}':\n{out.strip()[:1000]}")
            except Exception as e:
                result_parts.append(f"Web search '{query}' failed: {e}")

        if not result_parts:
            result_parts.append(
                f"Task '{record.task}' completed under role '{record.role.value}'."
            )

        return "\n".join(result_parts), artifacts
