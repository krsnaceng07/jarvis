"""jarvis.agents.sandbox.docker_backend — Docker/Podman container sandbox execution.

Mirrors OpenClaw's container execution path in ``docs/gateway/sandboxing.md``:
- Runs tools inside an isolated container (openclaw-sandbox:bookworm-slim).
- Applies --read-only rootfs, --cap-drop ALL, --network none, and /agent workspace mount.
- Translates workspace paths to /agent.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from src.agents.sessions.exec import ExecOptions, ExecResult, exec_command
from .context import SandboxContext
from .environment import sanitize_execution_environment


def is_container_engine_available(engine: str = "docker") -> bool:
    """Check if the requested container CLI is installed and responsive."""
    exe = shutil.which(engine)
    if not exe:
        return False
    try:
        res = subprocess.run([exe, "--version"], capture_output=True, timeout=3, check=False)
        return res.returncode == 0
    except Exception:
        return False


def is_container_running(container_name: str, engine: str = "docker") -> bool:
    """Check if a container is currently running."""
    exe = shutil.which(engine)
    if not exe:
        return False
    try:
        res = subprocess.run(
            [exe, "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return res.returncode == 0 and res.stdout.strip().lower() == "true"
    except Exception:
        return False


def ensure_sandbox_container(context: SandboxContext) -> str:
    """Ensure the sandbox container for context is started and reachable.

    Returns the running container name.
    """
    engine = context.backend if context.backend in ("docker", "podman") else "docker"
    container_name = context.container_name or f"jarvis-sandbox-{context.agent_id}"

    if is_container_running(container_name, engine):
        return container_name

    exe = shutil.which(engine)
    if not exe:
        raise RuntimeError(
            f"Sandbox backend '{engine}' is configured, but '{engine}' is not found on PATH. "
            f"Install {engine.capitalize()} or set agents.defaults.sandbox.mode='off'."
        )

    # Remove any dead/stopped container with the same name
    subprocess.run([exe, "rm", "-f", container_name], capture_output=True, check=False)

    docker_cfg = context.docker_config
    mount_mode = "ro" if context.workspace_access == "ro" else "rw"
    ws_host = str(context.workspace_path.resolve())

    # Build launch args mirroring OpenClaw
    run_cmd = [
        exe,
        "run",
        "-d",
        "--name",
        container_name,
        "--init",
        f"--network={docker_cfg.network}",
        "-v",
        f"{ws_host}:/agent:{mount_mode}",
        "-w",
        "/agent",
    ]

    if docker_cfg.read_only_root:
        run_cmd.append("--read-only")

    for tmp in docker_cfg.tmpfs:
        run_cmd.extend(["--tmpfs", tmp])

    for cap in docker_cfg.cap_drop:
        run_cmd.extend(["--cap-drop", cap])

    for bind in docker_cfg.binds:
        run_cmd.extend(["-v", bind])

    if docker_cfg.user:
        run_cmd.extend(["--user", docker_cfg.user])

    if docker_cfg.gpus:
        run_cmd.extend(["--gpus", docker_cfg.gpus])

    run_cmd.append(docker_cfg.image)
    run_cmd.extend(["sleep", "infinity"])

    res = subprocess.run(run_cmd, capture_output=True, text=True, timeout=30, check=False)
    if res.returncode != 0:
        raise RuntimeError(
            f"Failed to start sandbox container '{container_name}': {res.stderr.strip()}"
        )

    return container_name


def translate_path_to_sandbox(path: str | Path, workspace_root: Path) -> str:
    """Translate a host workspace path to the container /agent mount path."""
    p = Path(path).resolve()
    ws = workspace_root.resolve()
    if p == ws:
        return "/agent"
    try:
        rel = p.relative_to(ws)
        return f"/agent/{rel.as_posix()}"
    except ValueError:
        # Outside workspace: return original as-is
        return str(path)


def exec_in_sandbox(
    context: SandboxContext,
    command: str,
    args: list[str],
    cwd: str,
    options: ExecOptions | None = None,
    env_overrides: dict[str, str] | None = None,
) -> ExecResult:
    """Execute a command inside the active sandbox container."""
    engine = context.backend if context.backend in ("docker", "podman") else "docker"
    container_name = ensure_sandbox_container(context)

    container_cwd = translate_path_to_sandbox(cwd, context.workspace_path)
    clean_env = sanitize_execution_environment(overrides=env_overrides, is_sandboxed=True)

    # Build docker exec command
    exec_args = ["exec", "-i", "-w", container_cwd]
    for ek, ev in clean_env.items():
        exec_args.extend(["-e", f"{ek}={ev}"])

    exec_args.append(container_name)
    exec_args.append(command)
    exec_args.extend(args)

    return exec_command(
        command=engine,
        args=exec_args,
        cwd=str(context.workspace_path),
        options=options,
    )
