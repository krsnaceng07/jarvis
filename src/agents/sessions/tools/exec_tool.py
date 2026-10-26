"""jarvis.agents.sessions.tools.exec_tool — Built-in exec tool.

JARVIS canonical `exec` tool. Replaces the older `bash` tool surface,
providing extensive target capabilities, security profiles, and backgrounding.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from ..exec import (
    ExecOptions,
    exec_command,
    spawn_background_command,
)
from ..extensions.types import AgentToolResult, ToolDefinition
from .bash import resolve_bash_timeout_ms


def repair_cmd_syntax_to_powershell(command: str) -> str:
    """Auto-repair Windows CMD syntax constructs to idiomatic PowerShell."""
    # 1. Translate CMD 'if not exist <path> <action>' -> 'if (-not (Test-Path <path>)) { <action> }'
    def _rep_if_not_exist(m: re.Match) -> str:
        target = m.group(1).strip()
        action = m.group(2).strip()
        if action.startswith("(") and action.endswith(")"):
            action = action[1:-1].strip()
        md_match = re.match(r'^(?:mkdir|md)\s+("?[^"\r\n]+?"?|\S+)$', action, flags=re.I)
        if md_match:
            folder = md_match.group(1).strip()
            return f"if (-not (Test-Path {target})) {{ New-Item -ItemType Directory -Force -Path {folder} | Out-Null }}"
        return f"if (-not (Test-Path {target})) {{ {action} }}"

    command = re.sub(
        r'(?i)\bif\s+not\s+exist\s+("?[^"\r\n;]+?"?|\S+)\s+([^;\r\n]+)',
        _rep_if_not_exist,
        command,
    )

    # 2. Translate CMD 'if exist <path> <action>' -> 'if (Test-Path <path>) { <action> }'
    def _rep_if_exist(m: re.Match) -> str:
        target = m.group(1).strip()
        action = m.group(2).strip()
        if action.startswith("(") and action.endswith(")"):
            action = action[1:-1].strip()
        return f"if (Test-Path {target}) {{ {action} }}"

    command = re.sub(
        r'(?i)\bif\s+exist\s+("?[^"\r\n;]+?"?|\S+)\s+([^;\r\n]+)',
        _rep_if_exist,
        command,
    )

    # 3. Translate CMD 'type nul > <file>' to New-Item
    command = re.sub(
        r'(?i)\btype\s+nul\s*>\s*("?[^"\r\n;]+?"?|\S+)',
        r'New-Item -ItemType File -Force -Path \1 | Out-Null',
        command,
    )

    # 4. Translate CMD 'move /y' or 'move' with flags
    command = re.sub(r'(?i)\bmove\s+/y\s+', 'Move-Item -Force -Path ', command)

    # 5. Translate CMD 'copy /y' or 'copy' with flags
    command = re.sub(r'(?i)\bcopy\s+/y\s+', 'Copy-Item -Force -Path ', command)

    return command


def create_exec_tool_definition(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the :class:`ToolDefinition` for the exec tool."""
    options = options or {}

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        if signal is not None and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Operation aborted")

        command = params.get("command", "")
        if not command:
            raise ValueError("command is required")

        # 1. Resolve effective options & context
        opts = options or {}
        session_key = (
            params.get("session_key")
            or opts.get("session_key")
            or getattr(ctx, "session_key", None)
            or "agent:main:main"
        )
        agent_id = (
            opts.get("agent_id")
            or getattr(ctx, "agent_id", None)
            or (session_key.split(":")[1] if session_key.startswith("agent:") else "main")
        )
        sandbox_config = (
            opts.get("sandbox_config")
            or opts.get("config")
            or getattr(ctx, "sandbox_config", None)
            or getattr(ctx, "config", None)
        )
        creator_role = opts.get("creator_role") or getattr(ctx, "creator_role", None)
        creator_sandbox_policy = opts.get("creator_sandbox_policy") or getattr(
            ctx, "creator_sandbox_policy", None
        )
        workspace_root = cwd or getattr(ctx, "workspace", None) or os.getcwd()

        # 2. Resolve SandboxContext
        from ...sandbox import (
            evaluate_elevated_execution,
            evaluate_sandbox_tool_policy,
            exec_in_sandbox,
            resolve_sandbox_context,
            sanitize_execution_environment,
            validate_sandbox_path,
        )

        sandbox_ctx = resolve_sandbox_context(
            session_key=session_key,
            agent_id=agent_id,
            workspace_path=workspace_root,
            config=sandbox_config,
            creator_role=creator_role,
            creator_sandbox_policy=creator_sandbox_policy,
        )

        # 3. Evaluate Sandbox Tool Policy (tools.sandbox.tools allow/deny)
        tools_policy = (
            opts.get("tools_policy")
            or opts.get("tool_policy")
            or getattr(ctx, "tools_policy", None)
            or getattr(ctx, "tool_policy", None)
        )
        is_allowed, denial_reason = evaluate_sandbox_tool_policy(
            "exec",
            tools_policy,
            is_sandboxed=sandbox_ctx.is_sandboxed,
        )
        if not is_allowed:
            raise PermissionError(denial_reason or "Tool 'exec' is denied by sandbox tool policy.")

        # 4. Evaluate Elevated Execution and Target Host
        elevated_requested = bool(params.get("elevated", False))
        elevated_config = opts.get("elevated_config") or getattr(ctx, "elevated_config", None)
        sender_provider = (
            opts.get("sender_provider")
            or getattr(ctx, "sender_provider", None)
            or params.get("provider")
        )

        is_elevated_granted, refusal_reason = evaluate_elevated_execution(
            elevated_requested=elevated_requested,
            context=sandbox_ctx,
            elevated_config=elevated_config,
            sender_provider=sender_provider,
        )
        if elevated_requested and not is_elevated_granted:
            raise PermissionError(refusal_reason or "Elevated execution rejected.")

        host_target = params.get("host", "auto")
        if host_target == "gateway":
            if sandbox_ctx.creator_required:
                raise PermissionError(
                    "Host 'gateway' is blocked: session creator requires sandboxing."
                )
            if sandbox_ctx.is_sandboxed and not is_elevated_granted:
                raise PermissionError("Host 'gateway' requires elevated execution when sandboxed.")

        if is_elevated_granted or host_target == "gateway":
            effective_sandboxed = False
        elif host_target == "sandbox":
            effective_sandboxed = True
        else:
            effective_sandboxed = sandbox_ctx.is_sandboxed

        # 5. Working Directory & Filesystem Guard
        raw_workdir = params.get("workdir", cwd or os.getcwd())
        if effective_sandboxed:
            validated_workdir = validate_sandbox_path(
                raw_workdir,
                sandbox_ctx.workspace_path,
                is_mutation=False,
                access_mode=sandbox_ctx.workspace_access,
            )
            workdir = str(validated_workdir)
        else:
            workdir = raw_workdir
            if not os.path.isdir(workdir):
                raise FileNotFoundError(
                    f"Working directory does not exist: {workdir}\nCannot execute commands."
                )

        # 6. Sanitize Environment
        env_overrides = params.get("env")
        clean_env = sanitize_execution_environment(
            overrides=env_overrides,
            is_sandboxed=effective_sandboxed,
        )

        # 7. Check Host Security Policy
        if not effective_sandboxed:
            security_mode = (
                opts.get("security")
                or opts.get("mode")
                or getattr(ctx, "security", None)
                or getattr(ctx, "mode", None)
                or "full"
            )

            # Security "deny" rejects host execution unless explicitly elevated
            if security_mode == "deny" and not is_elevated_granted:
                raise PermissionError(
                    "Host execution is denied by security policy (security='deny')."
                )

            # In "allowlist" or "restrictive" mode, enforce safeBins / allowlist checks
            is_restrictive = security_mode in ("allowlist", "restrictive")
            if (
                hasattr(ctx, "permissions")
                and getattr(ctx.permissions, "mode", None) == "allow-all"
            ):
                is_restrictive = False
            if is_elevated_granted:
                is_restrictive = False

            if is_restrictive:
                import shlex

                from src.infra.exec_safe_bin_policy_profiles import SAFE_BIN_PROFILES
                from src.infra.exec_safe_bin_policy_validator import validate_safe_bin_argv

                try:
                    parsed_args = shlex.split(command, posix=True)
                except ValueError as e:
                    raise PermissionError(f"Rejected: Failed to parse command: {e}")

                if not parsed_args:
                    raise ValueError("command is empty after parsing")

                bin_name = parsed_args[0]
                bin_basename = os.path.basename(bin_name)

                allowlist = opts.get("allowlist") or getattr(ctx, "allowlist", [])
                if bin_basename in allowlist or bin_name in allowlist:
                    pass
                elif bin_basename not in SAFE_BIN_PROFILES:
                    raise PermissionError(
                        f"Command '{bin_name}' is not in safeBins and agent is in restrictive mode."
                    )
                else:
                    profile = SAFE_BIN_PROFILES[bin_basename]
                    if not validate_safe_bin_argv(parsed_args[1:], profile, bin_basename):
                        raise PermissionError(
                            f"Command '{command}' violates safeBins constraints for '{bin_basename}'."
                        )

        # 8. Timeout & Backgrounding setup
        timeout = params.get("timeout")
        timeout_ms = resolve_bash_timeout_ms(timeout)
        timeout_sec = timeout_ms / 1000.0 if timeout_ms else None

        background = params.get("background", False)
        yield_ms = params.get("yieldMs")
        _pty = params.get("pty", False)
        is_background = background or (yield_ms is not None and yield_ms >= 0)

        exec_options = ExecOptions(
            signal=signal,
            timeout=timeout_sec,
            cwd=workdir,
            env=clean_env,
        )

        import shutil
        import sys

        if sys.platform == "win32" and not effective_sandboxed:
            git_bash = None
            for candidate in (
                r"C:\Program Files\Git\bin\bash.exe",
                r"C:\Program Files (x86)\Git\bin\bash.exe",
                shutil.which("bash.exe"),
                shutil.which("bash"),
            ):
                if candidate and os.path.isfile(candidate):
                    git_bash = candidate
                    break

            cmd_stripped = command.strip()
            if git_bash and (
                params.get("shell") == "bash" or cmd_stripped.startswith(("bash ", "sh ", "./"))
            ):
                shell_cmd = git_bash
                args = ["-c", command]
            elif cmd_stripped.startswith(("cmd ", "cmd.exe ", "dir ", "echo %")):
                shell_cmd = "cmd.exe"
                args = ["/c", command]
            else:
                pwsh = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
                shell_cmd = pwsh

                from .path_utils import normalize_user_home_path

                repaired_command = command

                # 0. Expand CMD-style Windows environment variables (e.g. %USERPROFILE%, %APPDATA%, %TEMP%)
                # and tilde home directories (~/Downloads) because PowerShell does not expand %VAR% syntax.
                repaired_command = os.path.expandvars(repaired_command)
                repaired_command = re.sub(
                    r'(^|[\s"\'=])~([/\\])',
                    lambda m: f"{m.group(1)}{os.path.expanduser('~')}{m.group(2)}",
                    repaired_command,
                )

                # 1. Normalize hallucinated user home directories (e.g. C:\Users\rsnac -> C:\Users\kcs23)
                def _replace_user_path(m: re.Match) -> str:
                    return normalize_user_home_path(m.group(0))

                repaired_command = re.sub(
                    r"[a-zA-Z]:[/\\]Users[/\\][^\s\"';&|<>]+",
                    _replace_user_path,
                    repaired_command,
                )

                # 2. Map Unix open / xdg-open to Windows Invoke-Item
                repaired_command = re.sub(
                    r"^\s*(?:open|xdg-open)\s+",
                    "Invoke-Item ",
                    repaired_command,
                    flags=re.I,
                )

                # 3. Map Unix touch to PowerShell New-Item
                repaired_command = re.sub(
                    r"^\s*touch\s+",
                    "New-Item -ItemType File -Force -Path ",
                    repaired_command,
                    flags=re.I,
                )

                # 4. Auto-repair non-interactive deletion commands to prevent prompt stalls
                cmd_lower = repaired_command.lower()
                if any(k in cmd_lower for k in ("remove-item", "del ", "rmdir ", "rm ", "erase ")):
                    # Map Linux rm flags to PowerShell parameters
                    repaired_command = re.sub(
                        r"\brm\s+-(?:rf|fr)\s+",
                        "Remove-Item -Recurse -Force -Path ",
                        repaired_command,
                        flags=re.I,
                    )
                    repaired_command = re.sub(
                        r"\brm\s+-r\s+",
                        "Remove-Item -Recurse -Force -Path ",
                        repaired_command,
                        flags=re.I,
                    )
                    repaired_command = re.sub(
                        r"\brm\s+-f\s+",
                        "Remove-Item -Force -Path ",
                        repaired_command,
                        flags=re.I,
                    )

                    # Ensure Remove-Item has -Force and -Recurse
                    if "remove-item" in repaired_command.lower():
                        if "-force" not in repaired_command.lower():
                            repaired_command = re.sub(
                                r"\b(remove-item)\b", r"\1 -Force", repaired_command, flags=re.I
                            )
                        if "-recurse" not in repaired_command.lower():
                            repaired_command = re.sub(
                                r"\b(remove-item)\b", r"\1 -Recurse", repaired_command, flags=re.I
                            )

                    # Suppress all confirmation prompts in headless execution
                    repaired_command = f"$ConfirmPreference = 'None'; {repaired_command}"

                # 5. Replace Unix/CMD statement chaining '&&' with PowerShell statement separator ';'
                repaired_command = re.sub(r"\s*&&\s*", "; ", repaired_command)

                # 5b. Translate Windows CMD constructs (if not exist, if exist, move /y, etc.) to PowerShell
                repaired_command = repair_cmd_syntax_to_powershell(repaired_command)

                # 6. Guard against runaway recursive directory searches across root drives or Program Files
                # Restrict -Depth 3 ONLY to Get-ChildItem (or gci/dir/ls), NEVER to Remove-Item
                if (
                    re.search(r"(?i)\b(?:Get-ChildItem|gci)\b", repaired_command)
                    and "-depth" not in repaired_command.lower()
                ):
                    repaired_command = re.sub(
                        r"(?i)(\b(?:Get-ChildItem|gci)\b(?:(?!\||;).)*?\s*-recurse)\b",
                        r"\1 -Depth 3",
                        repaired_command,
                    )

                args = ["-NoProfile", "-NonInteractive", "-Command", repaired_command]
        else:
            shell_cmd = "/bin/sh"
            args = ["-c", command]

        # 9. Dispatch Execution
        if effective_sandboxed and sandbox_ctx.backend in ("docker", "podman"):
            result = exec_in_sandbox(
                context=sandbox_ctx,
                command="/bin/sh",
                args=["-c", command],
                cwd=workdir,
                options=exec_options,
                env_overrides=clean_env,
            )
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            if result.output_limit_exceeded:
                output += "\n[Truncated]"

            return {
                "content": [{"type": "text", "text": output}],
                "details": {
                    "exitCode": result.code,
                    "truncation": result.output_limit_exceeded is not None,
                    "sandboxed": True,
                    "container": sandbox_ctx.container_name,
                    "elevated": is_elevated_granted,
                },
            }

        if is_background:
            session_id = spawn_background_command(
                command=shell_cmd,
                args=args,
                cwd=workdir,
                options=exec_options,
                session_key=session_key,
            )
            output = (
                f"Process backgrounded. Session ID: {session_id}\n"
                f"Use the `process` tool to `poll` or `kill` this session."
            )
            return {
                "content": [{"type": "text", "text": output}],
                "details": {
                    "backgrounded": True,
                    "sessionId": session_id,
                    "sandboxed": False,
                    "elevated": is_elevated_granted,
                },
            }
        else:
            result = exec_command(
                command=shell_cmd,
                args=args,
                cwd=workdir,
                options=exec_options,
            )

            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            if result.output_limit_exceeded:
                output += "\n[Truncated]"

            if result.code != 0:
                output += f"\n[Process completed with exit code: {result.code}]"
                if "Invoke-WebRequest" in output or "ambiguous" in output:
                    output += "\n[HINT: In Windows PowerShell, 'curl' is an alias for Invoke-WebRequest. Use 'curl.exe' or invoke via Git Bash to run native cURL.]"
                elif "not recognized as the name of a cmdlet" in output:
                    output += "\n[HINT: Command not recognized in PowerShell. Try invoking with full extension (e.g. .exe), use Git Bash, or check PATH.]"

            return {
                "content": [{"type": "text", "text": output}],
                "details": {
                    "exitCode": result.code,
                    "truncation": result.output_limit_exceeded is not None,
                    "sandboxed": False,
                    "elevated": is_elevated_granted,
                },
            }

    return {
        "name": "exec",
        "label": "exec",
        "description": (
            "Run shell commands in the workspace. Supports foreground and background execution via `process`."
        ),
        "promptSnippet": "Execute a shell command",
        "promptGuidelines": [
            "Use exec to run shell commands in the foreground by default. Use background=True only for persistent servers, explicitly requested asynchronous work, or headless jobs that must outlive this turn."
        ],
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run."},
                "workdir": {"type": "string", "description": "Working directory."},
                "env": {"type": "object", "description": "Key/value environment overrides."},
                "yieldMs": {
                    "type": "integer",
                    "description": "Milliseconds to wait before backgrounding.",
                },
                "background": {"type": "boolean", "description": "Run in background immediately."},
                "timeout": {"type": "integer", "description": "Timeout in seconds."},
                "pty": {"type": "boolean", "description": "Run in a pseudo-terminal."},
                "elevated": {"type": "boolean", "description": "Run with elevated permissions."},
                "host": {"type": "string", "enum": ["auto", "sandbox", "gateway", "node"]},
                "security": {"type": "string"},
                "ask": {"type": "string"},
                "node": {"type": "string"},
            },
            "required": ["command"],
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


create_exec_tool = create_exec_tool_definition
