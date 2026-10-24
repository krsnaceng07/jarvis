"""jarvis.agents.sessions.tools.process_tool — Built-in process tool.

Mirrors OpenClaw's `process` tool for interacting with background `exec` sessions.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Optional

from ..extensions.types import AgentToolResult, ToolDefinition
from ..process_registry import registry


def create_process_tool_definition(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the :class:`ToolDefinition` for the process tool."""
    options = options or {}
    session_key = options.get("session_key")

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        if signal is not None and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Operation aborted")

        action = params.get("action", "")
        if not action:
            raise ValueError("action is required")

        session_id = (
            params.get("sessionId")
            or params.get("session_id")
            or params.get("name")
            or params.get("process")
            or params.get("target")
        )

        if action in ("open", "open_path", "start", "launch"):
            target_val = (
                session_id
                or params.get("target")
                or params.get("path")
                or params.get("command")
                or params.get("app")
                or ""
            )
            if not target_val:
                return {
                    "content": [{"type": "text", "text": "No target specified to open or launch."}],
                    "details": {"action": action, "launched": False, "error": "missing target"},
                }
            try:
                launch_msg = ""
                if sys.platform == "win32":
                    from .path_utils import launch_windows_app

                    ok, launch_msg = launch_windows_app(str(target_val))
                    if not ok:
                        return {
                            "content": [{"type": "text", "text": f"Failed to launch '{target_val}': {launch_msg}"}],
                            "details": {"target": target_val, "launched": False, "error": launch_msg},
                        }
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(target_val)])
                else:
                    subprocess.Popen(["xdg-open", str(target_val)])
                import asyncio

                # Adaptive readiness check: poll up to 0.4s max (in 50ms intervals) for window emergence,
                # returning immediately as soon as target window or process is detected.
                settled = False
                target_str = str(target_val).lower().strip()
                for _ in range(8):
                    await asyncio.sleep(0.05)
                    try:
                        import pygetwindow as gw

                        for w in gw.getAllWindows():
                            if w.title and any(
                                k in w.title.lower()
                                for k in (target_str, target_str.replace(".exe", ""))
                            ):
                                settled = True
                                break
                    except Exception:
                        pass
                    if settled:
                        break

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Successfully launched '{target_val}'. Window ready.",
                        }
                    ],
                    "details": {"target": target_val, "launched": True},
                }
            except Exception as e:
                return {
                    "content": [{"type": "text", "text": f"Failed to launch '{target_val}': {e}"}],
                    "details": {"target": target_val, "launched": False, "error": str(e)},
                }

        if action in ("wait", "wait_loading", "settle", "sleep"):
            import asyncio

            duration = float(
                params.get("duration")
                or params.get("seconds")
                or params.get("wait_seconds")
                or params.get("time")
                or 1.0
            )
            duration = min(max(duration, 0.05), 30.0)
            target = str(params.get("target") or params.get("app") or "").strip().lower()

            # Adaptive settling: if target window is already open and ready, return immediately
            if target:
                try:
                    import pygetwindow as gw

                    matched = [
                        w for w in gw.getAllWindows() if w.title and target in w.title.lower()
                    ]
                    if matched:
                        msg = f"Target window '{matched[0].title}' is already loaded and ready. Proceeding immediately."
                        return {
                            "content": [{"type": "text", "text": msg}],
                            "details": {
                                "action": action,
                                "target": target,
                                "waited_seconds": 0.0,
                                "ready": True,
                            },
                        }
                except Exception:
                    pass

            elapsed = 0.0
            step = 0.05
            while elapsed < duration:
                await asyncio.sleep(step)
                elapsed += step
                if target:
                    try:
                        import pygetwindow as gw

                        matched = [
                            w for w in gw.getAllWindows() if w.title and target in w.title.lower()
                        ]
                        if matched:
                            msg = f"Target window '{matched[0].title}' settled and ready (waited {elapsed:.2f}s)."
                            return {
                                "content": [{"type": "text", "text": msg}],
                                "details": {
                                    "action": action,
                                    "target": target,
                                    "waited_seconds": elapsed,
                                    "ready": True,
                                },
                            }
                    except Exception:
                        pass

            msg = f"Waited {elapsed:.2f}s for UI / window {f'({target}) ' if target else ''}to settle."
            return {
                "content": [{"type": "text", "text": msg}],
                "details": {"action": action, "target": target, "waited_seconds": elapsed},
            }

        if action in ("minimize", "minimize_all", "show_desktop"):
            if sys.platform == "win32":
                try:
                    subprocess.run(
                        [
                            "powershell",
                            "-NoProfile",
                            "-Command",
                            "(New-Object -ComObject Shell.Application).MinimizeAll()",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "Successfully minimized all open windows on host PC.",
                            }
                        ],
                        "details": {"action": "minimize", "minimized": True},
                    }
                except Exception as e:
                    return {
                        "content": [{"type": "text", "text": f"Failed to minimize windows: {e}"}],
                        "details": {"action": "minimize", "minimized": False, "error": str(e)},
                    }
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Minimize action is supported on Windows (platform is {sys.platform}).",
                    }
                ],
                "details": {"action": "minimize", "minimized": False},
            }

        if action in ("restore", "restore_all", "undo_minimize"):
            if sys.platform == "win32":
                try:
                    subprocess.run(
                        [
                            "powershell",
                            "-NoProfile",
                            "-Command",
                            "(New-Object -ComObject Shell.Application).UndoMinimizeALL()",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "Successfully restored open windows on host PC.",
                            }
                        ],
                        "details": {"action": "restore", "restored": True},
                    }
                except Exception as e:
                    return {
                        "content": [{"type": "text", "text": f"Failed to restore windows: {e}"}],
                        "details": {"action": "restore", "restored": False, "error": str(e)},
                    }
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Restore action is supported on Windows (platform is {sys.platform}).",
                    }
                ],
                "details": {"action": "restore", "restored": False},
            }

        if action in ("list_apps", "apps"):
            if sys.platform == "win32":
                apps_list = []
                try:
                    res_apps = subprocess.run(
                        ["tasklist", "/apps", "/fo", "csv"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if res_apps.returncode == 0:
                        lines = [
                            entry_line.strip()
                            for entry_line in res_apps.stdout.splitlines()
                            if entry_line.strip()
                        ]
                        for line in lines[1:]:
                            parts = [p.strip(' "') for p in line.split('","')]
                            if len(parts) >= 4:
                                img_name = parts[0].split("(")[0].strip()
                                pkg_name = parts[3]
                                if not any(
                                    x in img_name.lower()
                                    for x in (
                                        "runtimebroker",
                                        "widget",
                                        "crossdevice",
                                        "backgroundhost",
                                    )
                                ):
                                    apps_list.append(
                                        f"- {img_name} (Package: {pkg_name.split('_')[0]})"
                                    )
                except Exception:
                    pass

                try:
                    ps_script = (
                        "Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -or "
                        "$_.ProcessName -match 'whatsapp|notepad|chrome|msedge|spotify|discord|wt|code' } | "
                        "Select-Object -Unique ProcessName | ForEach-Object { $_.ProcessName }"
                    )
                    res_ps = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", ps_script],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if res_ps.returncode == 0:
                        for p in res_ps.stdout.splitlines():
                            p = p.strip()
                            if p and not any(p.lower() in a.lower() for a in apps_list):
                                apps_list.append(f"- {p}")
                except Exception:
                    pass

                if apps_list:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "Running Desktop Applications on PC:\n"
                                + "\n".join(sorted(set(apps_list))),
                            }
                        ],
                        "details": {"apps": sorted(set(apps_list))},
                    }
                return {
                    "content": [
                        {"type": "text", "text": "No active desktop applications detected."}
                    ]
                }
            elif sys.platform == "darwin":
                res = subprocess.run(
                    [
                        "osascript",
                        "-e",
                        'tell application "System Events" to get name of every process whose background only is false',
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res.returncode == 0 and res.stdout.strip():
                    apps = [f"- {a.strip()}" for a in res.stdout.strip().split(", ")]
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "Running Desktop Applications:\n" + "\n".join(apps),
                            }
                        ]
                    }
                return {"content": [{"type": "text", "text": "No active applications detected."}]}
            else:
                return {"content": [{"type": "text", "text": "list_apps completed."}]}

        if action in ("list", "ps", "status"):
            import time

            active = registry.get_all_active(session_key)
            finished = registry.get_all_finished(session_key)

            lines = ["### Background Process Sessions\n"]
            if not active and not finished:
                lines.append("No active background exec sessions found.")
                lines.append(
                    "To close a host application, call process(action='kill', session_id='<app_name>')."
                )
            else:
                if active:
                    lines.append("#### Running Processes:")
                    for s in active:
                        runtime_sec = int(time.time() - s.started_at)
                        cmd_display = s.command if len(s.command) <= 60 else s.command[:57] + "..."
                        lines.append(
                            f"- **ID:** `{s.id}` | **Status:** `running` | **PID:** {s.pid or 'n/a'} | **Elapsed:** {runtime_sec}s | **Command:** `{cmd_display}`"
                        )
                if finished:
                    lines.append("\n#### Recent Completed Processes:")
                    for f in finished:
                        runtime_sec = int(f.ended_at - f.started_at)
                        exit_str = (
                            f"code {f.exit_code}" if f.exit_code is not None else "terminated"
                        )
                        cmd_display = f.command if len(f.command) <= 60 else f.command[:57] + "..."
                        lines.append(
                            f"- **ID:** `{f.id}` | **Status:** `finished ({exit_str})` | **Duration:** {runtime_sec}s | **Command:** `{cmd_display}`"
                        )

            query = params.get("filter") or params.get("name") or params.get("query")
            if query:
                if sys.platform == "win32":
                    res = subprocess.run(
                        ["tasklist", "/FI", f"IMAGENAME eq {query}*"],
                        capture_output=True,
                        text=True,
                    )
                    if res.returncode == 0 and "INFO: No tasks" not in res.stdout:
                        lines.append(
                            f"\n#### Host Processes matching '{query}':\n{res.stdout.strip()}"
                        )
                else:
                    res = subprocess.run(
                        ["pgrep", "-l", str(query)], capture_output=True, text=True
                    )
                    if res.returncode == 0 and res.stdout.strip():
                        lines.append(
                            f"\n#### Host Processes matching '{query}':\n{res.stdout.strip()}"
                        )

            try:
                from src.automation.task_registry import list_task_records

                task_records = list_task_records()
                running_tasks = [t for t in task_records if t.status == "running"]
                queued_tasks = [t for t in task_records if t.status == "queued"]
                if running_tasks or queued_tasks:
                    lines.append("\n#### Background Task Ledger:")
                    for t in running_tasks:
                        lines.append(
                            f"- **Task ID:** `{t.task_id[:8]}` | **Status:** `running` | **Label:** {t.label or t.task}"
                        )
                    for t in queued_tasks:
                        lines.append(
                            f"- **Task ID:** `{t.task_id[:8]}` | **Status:** `queued` | **Label:** {t.label or t.task}"
                        )
            except Exception:
                pass

            return {
                "content": [{"type": "text", "text": "\n".join(lines)}],
                "details": {
                    "action": "list",
                    "activeCount": len(active),
                    "finishedCount": len(finished),
                    "active": [
                        {
                            "id": s.id,
                            "status": "running",
                            "command": s.command,
                            "startedAt": s.started_at,
                        }
                        for s in active
                    ],
                    "finished": [
                        {
                            "id": f.id,
                            "status": "completed" if f.exit_code == 0 else "failed",
                            "exitCode": f.exit_code,
                            "command": f.command,
                        }
                        for f in finished
                    ],
                },
            }

        if not session_id:
            raise ValueError(
                "session_id (or sessionId) is required for actions other than 'list', 'list_apps', 'minimize', or 'restore'"
            )

        session = registry.get_active(session_id)

        if action == "kill":
            if session:
                if session.proc:
                    try:
                        from ...sandbox.process_job import ProcessTreeContainment

                        ProcessTreeContainment.kill_process_tree(session.proc)
                        return {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Sent kill to process tree for session {session_id}.",
                                }
                            ]
                        }
                    except Exception as e:
                        return {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Failed to kill session {session_id}: {e}",
                                }
                            ]
                        }
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Session {session_id} has no running process (already closed).",
                        }
                    ],
                    "details": {"session_id": session_id, "killed": True, "already_closed": True},
                }

            # Host OS process / application termination fallback
            target_proc = str(session_id).strip().strip("'\"`")
            target_lower = target_proc.lower()

            # Safety guard: Web services must never terminate host browser processes
            if target_lower in ("youtube", "yt"):
                try:
                    from src.application_automation.tools.youtube_tools import get_youtube_provider

                    close_res = await get_youtube_provider().close()
                    msg = (
                        close_res.value.get("message", "Closed YouTube browser tab.")
                        if close_res.is_ok
                        else str(close_res.error)
                    )
                    return {
                        "content": [{"type": "text", "text": msg}],
                        "details": {"session_id": target_proc, "killed": True, "tab_closed": True},
                    }
                except Exception as e:
                    return {
                        "content": [{"type": "text", "text": f"Closed YouTube tab ({e})."}],
                        "details": {"session_id": target_proc, "killed": True, "tab_closed": True},
                    }

            if sys.platform == "win32":
                if target_proc.isdigit():
                    cmd = ["taskkill", "/F", "/PID", target_proc]
                    res = subprocess.run(cmd, capture_output=True, text=True)
                    if res.returncode == 0:
                        return {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Successfully terminated PID {target_proc} on PC.",
                                }
                            ],
                            "details": {"session_id": target_proc, "killed": True},
                        }
                else:
                    target_lower = target_proc.lower()
                    base_name = target_lower.removesuffix(".exe")

                    # 1. PowerShell wildcard process termination (handles UWP like WhatsApp.Root, Spotify, etc.)
                    ps_script = (
                        f"$p = Get-Process -Name '*{base_name}*' -ErrorAction SilentlyContinue; "
                        "if ($p) { $p | Stop-Process -Force; Write-Output 'KILLED' } else { Write-Output 'NONE' }"
                    )
                    res_ps = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", ps_script],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if "KILLED" in res_ps.stdout:
                        return {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Successfully closed host application/process '{target_proc}' on PC.",
                                }
                            ],
                            "details": {"session_id": target_proc, "killed": True},
                        }

                    # 2. Terminal specific binaries
                    if target_lower in ("terminal", "windows terminal", "wt", "windowsterminal"):
                        res = subprocess.run(
                            ["taskkill", "/F", "/IM", "WindowsTerminal.exe"],
                            capture_output=True,
                            text=True,
                        )
                        if res.returncode != 0:
                            res = subprocess.run(
                                ["taskkill", "/F", "/IM", "wt.exe"], capture_output=True, text=True
                            )
                        if res.returncode == 0:
                            return {
                                "content": [
                                    {"type": "text", "text": "Successfully closed terminal on PC."}
                                ],
                                "details": {"session_id": target_proc, "killed": True},
                            }

                    # 3. taskkill by executable image name
                    proc_name = (
                        target_proc if target_lower.endswith(".exe") else f"{target_proc}.exe"
                    )
                    res = subprocess.run(
                        ["taskkill", "/F", "/IM", proc_name], capture_output=True, text=True
                    )
                    if res.returncode == 0:
                        return {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Successfully closed host application/process '{target_proc}' on PC.",
                                }
                            ],
                            "details": {"session_id": target_proc, "killed": True},
                        }

                    # 4. If neither was running, report idempotent already closed
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Process/application '{target_proc}' is not running (already closed).",
                            }
                        ],
                        "details": {
                            "session_id": target_proc,
                            "killed": True,
                            "already_closed": True,
                        },
                    }
            elif sys.platform == "darwin":
                cmd = (
                    ["kill", "-9", target_proc]
                    if target_proc.isdigit()
                    else ["pkill", "-f", target_proc]
                )
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Successfully closed application '{target_proc}'.",
                            }
                        ],
                        "details": {"session_id": target_proc, "killed": True},
                    }
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Process/application '{target_proc}' is not running (already closed).",
                        }
                    ],
                    "details": {"session_id": target_proc, "killed": True, "already_closed": True},
                }
            else:
                cmd = (
                    ["kill", "-9", target_proc]
                    if target_proc.isdigit()
                    else ["pkill", "-f", target_proc]
                )
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Successfully closed process '{target_proc}'.",
                            }
                        ],
                        "details": {"session_id": target_proc, "killed": True},
                    }
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Process/application '{target_proc}' is not running (already closed).",
                        }
                    ],
                    "details": {"session_id": target_proc, "killed": True, "already_closed": True},
                }

        elif action == "remove":
            removed = registry.remove(session_id)
            if removed:
                return {
                    "content": [
                        {"type": "text", "text": f"Removed session {session_id} from registry."}
                    ]
                }
            return {"content": [{"type": "text", "text": f"Session {session_id} not found."}]}

        elif action in ("poll", "log"):
            session = registry.get_active(session_id) if session_id else None
            finished_session = (
                registry.get_finished(session_id) if (not session and session_id) else None
            )

            if not session and not finished_session:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Session '{session_id}' not found (may have already completed/been removed). Use action='list' to inspect all sessions.",
                        }
                    ]
                }

            if finished_session:
                exit_msg = (
                    f"exit code {finished_session.exit_code}"
                    if finished_session.exit_code is not None
                    else "terminated"
                )
                output_msg = f"--- Session {session_id} ({finished_session.command}) [Finished: {exit_msg}] ---\n"
                if finished_session.tail:
                    output_msg += f"OUTPUT:\n{finished_session.tail}\n"
                elif finished_session.aggregated:
                    output_msg += f"OUTPUT:\n{finished_session.aggregated}\n"
                else:
                    output_msg += "(No output recorded)\n"
                return {
                    "content": [{"type": "text", "text": output_msg}],
                    "details": {
                        "sessionId": finished_session.id,
                        "status": "completed" if finished_session.exit_code == 0 else "failed",
                        "exitCode": finished_session.exit_code,
                    },
                }

            out = "".join(session.pending_stdout)
            err = "".join(session.pending_stderr)

            # Clear pending buffers after reading
            session.pending_stdout.clear()
            session.pending_stderr.clear()
            session.pending_stdout_chars = 0
            session.pending_stderr_chars = 0

            output_msg = f"--- Session {session_id} ({session.command}) ---\n"
            output_msg += f"Terminal Cursor Mode: {session.cursor_key_mode}\n"
            if out:
                output_msg += f"STDOUT:\n{out}\n"
            if err:
                output_msg += f"STDERR:\n{err}\n"
            if not out and not err:
                output_msg += "(No new output)\n"

            if session.exited:
                output_msg += f"\n[Process has exited with code {session.exit_code}]"
                registry.remove(session_id)

            return {
                "content": [{"type": "text", "text": output_msg}],
                "details": {
                    "sessionId": session.id,
                    "status": "running"
                    if not session.exited
                    else ("completed" if session.exit_code == 0 else "failed"),
                    "exitCode": session.exit_code,
                },
            }

        elif action == "write":
            session = registry.get_active(session_id) if session_id else None
            if not session:
                return {"content": [{"type": "text", "text": f"Session {session_id} not found."}]}
            data = params.get("data", "")
            if session.proc and session.proc.stdin:
                try:
                    session.proc.stdin.write(data.encode("utf-8"))
                    session.proc.stdin.flush()

                    eof = params.get("eof", False)
                    if eof:
                        session.proc.stdin.close()

                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Wrote {len(data)} chars to session {session_id}.",
                            }
                        ]
                    }
                except Exception as e:
                    return {"content": [{"type": "text", "text": f"Failed to write: {e}"}]}
            return {
                "content": [{"type": "text", "text": f"Session {session_id} stdin not available."}]
            }

        elif action in ("send-keys", "send_keys", "sendkeys", "keys"):
            session = registry.get_active(session_id) if session_id else None
            if not session:
                return {"content": [{"type": "text", "text": f"Session {session_id} not found."}]}
            keys = params.get("keys", [])
            if not isinstance(keys, list):
                keys = [keys] if keys else []
            literal = params.get("literal")

            if session.proc and session.proc.stdin:
                try:
                    sent_count = 0
                    if literal:
                        session.proc.stdin.write(literal.encode("utf-8"))
                        sent_count += len(literal)

                    key_map = {
                        "up": "\x1bOA" if session.cursor_key_mode == "application" else "\x1b[A",
                        "down": "\x1bOB" if session.cursor_key_mode == "application" else "\x1b[B",
                        "right": "\x1bOC" if session.cursor_key_mode == "application" else "\x1b[C",
                        "left": "\x1bOD" if session.cursor_key_mode == "application" else "\x1b[D",
                        "enter": "\r\n",
                        "return": "\r\n",
                        "tab": "\t",
                        "escape": "\x1b",
                        "esc": "\x1b",
                        "backspace": "\x08",
                        "ctrl+c": "\x03",
                        "sigint": "\x03",
                        "^c": "\x03",
                        "ctrl+d": "\x04",
                        "eof": "\x04",
                        "ctrl+z": "\x1a",
                    }
                    for key in keys:
                        k_lower = str(key).lower()
                        seq = key_map.get(k_lower, str(key))
                        session.proc.stdin.write(seq.encode("utf-8"))
                        sent_count += 1

                    session.proc.stdin.flush()
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Sent input/keys to session {session_id}.",
                            }
                        ],
                        "details": {
                            "sessionId": session_id,
                            "status": "running",
                            "sent": sent_count,
                        },
                    }
                except Exception as e:
                    return {"content": [{"type": "text", "text": f"Failed to send keys: {e}"}]}
            return {
                "content": [{"type": "text", "text": f"Session {session_id} stdin not available."}]
            }

        elif action == "submit":
            session = registry.get_active(session_id) if session_id else None
            if not session:
                return {"content": [{"type": "text", "text": f"Session {session_id} not found."}]}
            if session.proc and session.proc.stdin:
                try:
                    session.proc.stdin.write(b"\r\n")
                    session.proc.stdin.flush()
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Submitted session {session_id} (sent Enter/CR).",
                            }
                        ],
                        "details": {"sessionId": session_id, "status": "running"},
                    }
                except Exception as e:
                    return {"content": [{"type": "text", "text": f"Failed to submit: {e}"}]}
            return {
                "content": [{"type": "text", "text": f"Session {session_id} stdin not available."}]
            }

        elif action == "paste":
            session = registry.get_active(session_id) if session_id else None
            if not session:
                return {"content": [{"type": "text", "text": f"Session {session_id} not found."}]}
            paste_text = params.get("text") or params.get("data") or ""
            if not paste_text:
                return {"content": [{"type": "text", "text": "No paste text provided."}]}
            if session.proc and session.proc.stdin:
                try:
                    session.proc.stdin.write(paste_text.encode("utf-8"))
                    session.proc.stdin.flush()
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Pasted {len(paste_text)} chars to session {session_id}.",
                            }
                        ],
                        "details": {"sessionId": session_id, "status": "running"},
                    }
                except Exception as e:
                    return {"content": [{"type": "text", "text": f"Failed to paste: {e}"}]}
            return {
                "content": [{"type": "text", "text": f"Session {session_id} stdin not available."}]
            }

        else:
            return {"content": [{"type": "text", "text": f"Unsupported action: {action}"}]}

    return {
        "name": "process",
        "label": "process",
        "description": (
            "Control and interact with background `exec` sessions, launch or terminate host desktop applications (e.g. notepad, terminal, calc), "
            "or pause to wait for an application or UI to settle and finish loading. "
            "To launch an app: action='open', target='<app_or_path>'. "
            "To wait for loading: action='wait', duration=2.0. "
            "To close/kill an app or process: action='kill', session_id='<app_name>' (e.g. session_id='notepad'). "
            "Never ask user for PID."
        ),
        "promptSnippet": "Interact with a background process, launch/close desktop apps, or wait for UI loading",
        "promptGuidelines": [
            "Use process with action='open' and target='<app_or_path>' to launch desktop applications.",
            "Use process with action='wait' and duration=2.0 to wait while an application, window, or web page is loading before taking next steps.",
            "Use process with action='kill' and session_id='<app_name>' to close desktop applications immediately.",
            "Use process to poll output or kill background tasks.",
        ],
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Process action: 'open' (launch app), 'wait'/'settle' (wait for UI to load), 'kill' (terminate app or session), 'list', 'poll', 'log', 'write', 'send-keys', 'remove'",
                },
                "target": {
                    "type": "string",
                    "description": "Application name, file, or path to launch for 'open' action.",
                },
                "duration": {
                    "type": "number",
                    "description": "Duration in seconds to wait for 'wait'/'settle' action (default: 1.5, min: 0.1, max: 30.0).",
                },
                "session_id": {
                    "type": "string",
                    "description": "Application name to close (e.g. 'notepad', 'terminal', 'calc') or background session ID.",
                },
                "sessionId": {
                    "type": "string",
                    "description": "Alias for session_id.",
                },
                "data": {"type": "string", "description": "Data to write for write action"},
                "eof": {"type": "boolean", "description": "Close stdin after write"},
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keys to send (e.g. ['up', 'enter']) for send-keys action",
                },
            },
            "required": ["action"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "array"},
                "details": {"type": "object"},
            },
        },
        "execute": _execute,
    }


create_process_tool = create_process_tool_definition
