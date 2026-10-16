"""Managed Codex app-server health check for `jarvis doctor --lint --only codex/managed-app-server`.

OpenClaw parity: ``extensions/codex/src/doctor.ts``.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from extensions.codex.src.app_server.managed_binary import (
    attest_codex_launcher,
    find_managed_codex_app_server_command_path,
    is_managed_codex_desktop_command,
)
from extensions.codex.src.app_server.version import (
    CODEX_APP_SERVER_VERSION,
    MIN_SUPPORTED_CODEX_APP_SERVER_VERSION,
)

CODEX_MANAGED_APP_SERVER_CHECK_ID: str = "codex/managed-app-server"
CODEX_VERSION_TIMEOUT_SECONDS: float = 5.0


@dataclass(frozen=True, slots=True)
class HealthFinding:
    """Finding returned by a doctor health check."""

    check_id: str
    severity: str  # "error" | "warning" | "info"
    source: str
    message: str
    path: str | None = None
    requirement: str | None = None
    fix_hint: str | None = None


def parse_codex_version(output: str) -> str | None:
    """Extract semantic version string from `codex --version` output."""
    match = re.search(
        r"(?:^|\s)v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)(?:\s|$)",
        output,
    )
    return match.group(1) if match else None


def _default_run_version_command(command: str) -> str:
    """Run `command --version` and return stdout.

    Attests inherited ``NODE_OPTIONS`` first: code-loading options fail
    closed here exactly as in app-server startup (runtime-artifact.ts).
    """
    from extensions.codex.src.app_server.node_options import (  # noqa: PLC0415
        assert_safe_node_options_env,
    )

    assert_safe_node_options_env(os.environ)
    res = subprocess.run(
        [command, "--version"],
        capture_output=True,
        text=True,
        timeout=CODEX_VERSION_TIMEOUT_SECONDS,
    )
    return res.stdout or res.stderr or ""


def check_codex_managed_app_server(
    plugin_root: str | None = None,
    config: dict[str, Any] | None = None,
    version_runner: Callable[[str], str] | None = None,
) -> list[HealthFinding]:
    """Execute the `codex/managed-app-server` health check.

    OpenClaw parity: ``createCodexManagedAppServerHealthCheck`` in ``src/doctor.ts``.
    """
    findings: list[HealthFinding] = []
    runner = version_runner or _default_run_version_command

    cmd_path = find_managed_codex_app_server_command_path(plugin_root=plugin_root)

    if not cmd_path or not os.path.exists(cmd_path):
        findings.append(
            HealthFinding(
                check_id=CODEX_MANAGED_APP_SERVER_CHECK_ID,
                severity="error",
                source="codex",
                message="Managed Codex app-server binary not found at target candidates.",
                path=plugin_root or "extensions/codex",
                requirement=f"an executable Codex {CODEX_APP_SERVER_VERSION} managed artifact",
                fix_hint=(
                    "Reinstall the staged OpenClaw package with its @openai/codex platform dependency, "
                    "then rerun the candidate check."
                ),
            )
        )
        return findings

    attestation = attest_codex_launcher(cmd_path, plugin_root=plugin_root)
    if not attestation.get("ok"):
        findings.append(
            HealthFinding(
                check_id=CODEX_MANAGED_APP_SERVER_CHECK_ID,
                severity="error",
                source="codex",
                message=(
                    "Managed Codex app-server launcher is unverified: "
                    f"{attestation.get('reason', 'wrapper script or unknown binary')} . "
                    "Only Desktop, vendor/bin, PATH, or the official @openai/codex package entrypoints are allowed."
                ),
                path=cmd_path,
                requirement="official @openai/codex package or approved managed launcher",
                fix_hint="Replace the wrapper binary with the official Codex launcher path or reinstall the managed package.",
            )
        )
        return findings

    # Desktop binaries bypass version pin strictness if valid
    if is_managed_codex_desktop_command(cmd_path):
        return findings

    try:
        raw_output = runner(cmd_path)
        parsed = parse_codex_version(raw_output)
    except Exception as e:
        findings.append(
            HealthFinding(
                check_id=CODEX_MANAGED_APP_SERVER_CHECK_ID,
                severity="error",
                source="codex",
                message=f"Failed to execute version check for managed Codex app-server: {e}",
                path=cmd_path,
                requirement=f"Codex app-server >= {MIN_SUPPORTED_CODEX_APP_SERVER_VERSION}",
                fix_hint="Ensure the executable has correct permissions and platform compatibility.",
            )
        )
        return findings

    if not parsed:
        findings.append(
            HealthFinding(
                check_id=CODEX_MANAGED_APP_SERVER_CHECK_ID,
                severity="error",
                source="codex",
                message=f"Managed Codex app-server returned unparseable version output: {raw_output.strip()!r}",
                path=cmd_path,
                requirement=f"Codex app-server version output containing semantic version (e.g. {CODEX_APP_SERVER_VERSION})",
                fix_hint="Verify that the executable is a valid Codex app-server binary.",
            )
        )
        return findings

    # Compare version against floor and pinned version
    def _parse_tuple(ver_str: str) -> tuple[int, ...]:
        clean = ver_str.split("-")[0].split("+")[0]
        return tuple(int(x) for x in clean.split("."))

    try:
        ver_tuple = _parse_tuple(parsed)
        floor_tuple = _parse_tuple(MIN_SUPPORTED_CODEX_APP_SERVER_VERSION)
        pinned_tuple = _parse_tuple(CODEX_APP_SERVER_VERSION)

        if ver_tuple < floor_tuple:
            findings.append(
                HealthFinding(
                    check_id=CODEX_MANAGED_APP_SERVER_CHECK_ID,
                    severity="error",
                    source="codex",
                    message=f"Managed Codex app-server version {parsed} is below minimum supported version {MIN_SUPPORTED_CODEX_APP_SERVER_VERSION}.",
                    path=cmd_path,
                    requirement=f">= {MIN_SUPPORTED_CODEX_APP_SERVER_VERSION}",
                    fix_hint=f"Upgrade Codex app-server binary to {CODEX_APP_SERVER_VERSION}.",
                )
            )
        elif ver_tuple > pinned_tuple:
            findings.append(
                HealthFinding(
                    check_id=CODEX_MANAGED_APP_SERVER_CHECK_ID,
                    severity="info",
                    source="codex",
                    message=f"Managed Codex app-server version {parsed} is newer than pinned version {CODEX_APP_SERVER_VERSION}. Continuing with compatibility warning.",
                    path=cmd_path,
                    requirement=f"== {CODEX_APP_SERVER_VERSION}",
                    fix_hint="No action required if runtime validation succeeds.",
                )
            )
    except Exception:
        pass

    return findings


def check_codex_app_server_launch_config(
    plugin_config: dict[str, Any] | None = None,
    env: dict[str, Any] | None = None,
) -> list[HealthFinding]:
    """Validate app-server launch configuration (verified-setup rules).

    Mirrors the setup-time throws in ``config-options.ts`` /
    ``config-parsing.ts`` as doctor findings instead: command overrides
    must be bare executable paths (inline args move to ``args``), and
    ``sessionCatalog.homes`` requires ``stdio`` transport.
    """
    from extensions.codex.src.app_server.config import (  # noqa: PLC0415
        read_codex_plugin_config,
    )
    from extensions.codex.src.app_server.launch_policy import (  # noqa: PLC0415
        assert_no_inline_args,
    )

    findings: list[HealthFinding] = []
    raw_app = (plugin_config or {}).get("appServer", (plugin_config or {}).get("app_server", {}))
    if isinstance(raw_app, dict) and raw_app.get("approvalPolicy") == "untrusted":
        findings.append(
            HealthFinding(
                check_id=CODEX_MANAGED_APP_SERVER_CHECK_ID,
                severity="error",
                source="codex",
                message=(
                    'plugins.entries.codex.config.appServer.approvalPolicy="untrusted" '
                    'is retired; use "on-request".'
                ),
                path="plugins.entries.codex.config.appServer.approvalPolicy",
                fix_hint='Set approvalPolicy to "on-request".',
            )
        )
    # env=None reads process env inside the parser (live validation);
    # tests pass explicit dicts for hermetic checks.
    cfg = read_codex_plugin_config(plugin_config or {}, env=env)
    command = cfg.app_server.command
    if command:
        # The parser records which surface supplied the command by
        # precedence: explicit config wins, else the env override.
        raw = plugin_config or {}
        app_raw = raw.get("appServer", raw.get("app_server", {}))
        source = "config" if isinstance(app_raw, dict) and app_raw.get("command") else "env"
        try:
            assert_no_inline_args(command, source=source)
        except ValueError as e:
            findings.append(
                HealthFinding(
                    check_id=CODEX_MANAGED_APP_SERVER_CHECK_ID,
                    severity="error",
                    source="codex",
                    message=str(e),
                    path="plugins.entries.codex.config.appServer.command",
                    fix_hint="Move inline arguments to appServer.args (or "
                    "OPENCLAW_CODEX_APP_SERVER_ARGS).",
                )
            )
    if cfg.session_catalog.homes and cfg.app_server.transport != "stdio":
        findings.append(
            HealthFinding(
                check_id=CODEX_MANAGED_APP_SERVER_CHECK_ID,
                severity="error",
                source="codex",
                message=(
                    "plugins.entries.codex.config.sessionCatalog.homes requires "
                    "appServer.transport=stdio."
                ),
                path="plugins.entries.codex.config.sessionCatalog.homes",
                fix_hint="Set appServer.transport to stdio or remove sessionCatalog.homes.",
            )
        )
    return findings


__all__ = [
    "CODEX_MANAGED_APP_SERVER_CHECK_ID",
    "HealthFinding",
    "check_codex_app_server_launch_config",
    "check_codex_managed_app_server",
    "parse_codex_version",
]
