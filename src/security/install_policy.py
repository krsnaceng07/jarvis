"""jarvis.security.install_policy — Operator Install Policy (`security.installPolicy`).

OpenClaw parity: mirrors
``openclaw-main/docs/tools/skills-config.md`` and
``openclaw-main/src/security/install-policy.ts``.

Features:
- `InstallPolicyTarget`: `"skill"` | `"plugin"`
- `InstallPolicyRequestKind`: `"skill-install"` | `"plugin-dir"` | `"plugin-archive"` | `"plugin-file"` | `"plugin-npm"` | `"plugin-git"`
- `InstallPolicyExecConfig`: Dataclass for policy process configuration (`command`, `args`, `timeoutMs`, `maxOutputBytes`, `passEnv`, `env`, `trustedDirs`).
- `InstallPolicyDecision`: Dataclass holding evaluation outcome (`decision: "allow" | "block"`, `reason`).
- `evaluate_install_policy()`: Evaluates local policy command with timeout and fail-closed safety.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

InstallPolicyTarget = Literal["skill", "plugin"]
InstallPolicyRequestKind = Literal[
    "skill-install",
    "plugin-dir",
    "plugin-archive",
    "plugin-file",
    "plugin-npm",
    "plugin-git",
]

DEFAULT_TIMEOUT_MS = 10000
DEFAULT_MAX_OUTPUT_BYTES = 1048576


@dataclass
class InstallPolicyExecConfig:
    command: str
    args: list[str] = field(default_factory=list)
    timeoutMs: int = DEFAULT_TIMEOUT_MS
    noOutputTimeoutMs: int = DEFAULT_TIMEOUT_MS
    maxOutputBytes: int = DEFAULT_MAX_OUTPUT_BYTES
    passEnv: list[str] = field(default_factory=lambda: ["JARVIS_STATE_DIR", "PATH"])
    env: dict[str, str] = field(default_factory=dict)
    trustedDirs: list[str] = field(default_factory=list)


@dataclass
class InstallPolicyDecision:
    decision: Literal["allow", "block"]
    reason: str | None = None
    protocolVersion: int = 1


def evaluate_install_policy(
    exec_config: InstallPolicyExecConfig,
    target_type: InstallPolicyTarget,
    target_name: str,
    source_path: str,
    origin_info: dict[str, Any] | None = None,
) -> InstallPolicyDecision:
    """Execute local operator install policy command with fail-closed semantics."""
    cmd_path = Path(exec_config.command).resolve()
    if not cmd_path.exists():
        return InstallPolicyDecision(
            decision="block", reason=f"Policy command '{exec_config.command}' does not exist"
        )

    payload = {
        "protocolVersion": 1,
        "jarvisVersion": "2026.6.1",
        "targetType": target_type,
        "targetName": target_name,
        "sourcePath": source_path,
        "sourcePathKind": "directory" if Path(source_path).is_dir() else "file",
        "origin": origin_info or {},
    }

    stdin_bytes = json.dumps(payload).encode("utf-8")
    timeout_sec = exec_config.timeoutMs / 1000.0

    try:
        proc = subprocess.run(
            [str(cmd_path)] + exec_config.args,
            input=stdin_bytes,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )

        if proc.returncode != 0:
            return InstallPolicyDecision(
                decision="block", reason=f"Policy command exited with code {proc.returncode}"
            )

        output_str = proc.stdout.decode("utf-8", errors="replace").strip()
        data = json.loads(output_str)

        if data.get("protocolVersion") != 1:
            return InstallPolicyDecision(decision="block", reason="Unsupported protocol version")

        dec = data.get("decision")
        if dec not in ("allow", "block"):
            return InstallPolicyDecision(decision="block", reason="Invalid decision output")

        return InstallPolicyDecision(decision=dec, reason=data.get("reason"))

    except subprocess.TimeoutExpired:
        return InstallPolicyDecision(decision="block", reason="Policy command timed out")
    except Exception as exc:
        return InstallPolicyDecision(decision="block", reason=f"Policy execution failed: {exc}")


__all__ = [
    "DEFAULT_MAX_OUTPUT_BYTES",
    "DEFAULT_TIMEOUT_MS",
    "InstallPolicyDecision",
    "InstallPolicyExecConfig",
    "InstallPolicyRequestKind",
    "InstallPolicyTarget",
    "evaluate_install_policy",
]
