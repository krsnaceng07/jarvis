"""Codex Computer Use status types.

OpenClaw parity: ``CodexComputerUseStatus`` and all discriminated union
members in ``extensions/codex/src/app-server/computer-use.ts``.

All discriminant literals are kept identical to the TypeScript source so that
serialised status payloads are wire-compatible when forwarded over the JARVIS
gateway protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


# ── reason codes (verbatim from OpenClaw) ────────────────────────────────────

StatusReason = Literal[
    "disabled",
    "marketplace_missing",
    "plugin_not_installed",
    "plugin_disabled",
    "mcp_missing",
    "live_test_failed",
    "ready",
    "check_failed",
    "auto_install_blocked",
]

InstallationStatusCode = Literal[
    "disabled",
    "marketplace_missing",
    "not_installed",
    "installed_disabled",
    "installed",
]

ExposureStatusCode = Literal["skipped", "missing", "available"]

LiveTestState = Literal["skipped", "passed", "failed"]


# ── section sub-types ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StatusSection:
    """Generic ``status/ok/message`` section — maps to OpenClaw's ``CodexComputerUseStatusSection``."""

    status: str
    ok: bool
    message: str


@dataclass(frozen=True, slots=True)
class InstallationStatus:
    """Installation section with a typed status code.

    Flat (not subclassing StatusSection) so Python's default-after-non-default
    rule is not violated while still keeping a typed ``status`` discriminant.
    """

    status: InstallationStatusCode
    ok: bool
    message: str


@dataclass(frozen=True, slots=True)
class ExposureStatus:
    """MCP exposure section with a typed status code."""

    status: ExposureStatusCode
    ok: bool
    message: str


@dataclass(frozen=True, slots=True)
class RepairStatus:
    """Post-repair outcome — mirrors OpenClaw's ``CodexComputerUseRepairStatus``."""

    attempted: bool
    killed_pids: list[int]
    message: str
    warnings: list[str]


@dataclass(frozen=True, slots=True)
class LiveTestStatus:
    """Live-test outcome — mirrors OpenClaw's ``CodexComputerUseLiveTestStatus``."""

    status: LiveTestState
    ok: bool
    attempted: bool
    attempts: int
    timeout_ms: int
    retried: bool
    repaired: bool
    message: str
    error: Optional[str] = None
    duration_ms: Optional[int] = None


# ── top-level status ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CodexComputerUseStatus:
    """Top-level Computer Use readiness status.

    OpenClaw parity: ``CodexComputerUseStatus`` in ``computer-use.ts``.
    All field names are snake_case translations of the camelCase TypeScript
    fields; the serialised wire format should camelCase them on export.
    """

    enabled: bool
    ready: bool
    reason: StatusReason
    installed: bool
    plugin_enabled: bool
    mcp_server_available: bool
    plugin_name: str
    mcp_server_name: str
    tools: list[str]
    installation: InstallationStatus
    exposure: ExposureStatus
    live_test: LiveTestStatus
    warnings: list[str]
    message: str
    marketplace_name: Optional[str] = None
    marketplace_path: Optional[str] = None
    repair: Optional[RepairStatus] = None


def format_status_markdown(status: CodexComputerUseStatus) -> str:
    """Format top-level Computer Use status into readable markdown."""
    icon = "✅" if status.ready else "❌"
    tools_str = ", ".join(f"`{t}`" for t in status.tools) if status.tools else "None"
    return (
        f"**Codex Computer Use Status** {icon}\n\n"
        f"- **Reason:** `{status.reason}`\n"
        f"- **Message:** {status.message}\n"
        f"- **Plugin:** `{status.plugin_name}` (installed: {status.installed}, enabled: {status.plugin_enabled})\n"
        f"- **MCP Server:** `{status.mcp_server_name}` (available: {status.mcp_server_available})\n"
        f"- **Available Tools:** {tools_str}\n"
        f"- **Live Test:** `{status.live_test.status}` ({status.live_test.message})"
    )


format_computer_use_status_markdown = format_status_markdown

__all__ = [
    "CodexComputerUseStatus",
    "ExposureStatus",
    "ExposureStatusCode",
    "InstallationStatus",
    "InstallationStatusCode",
    "LiveTestState",
    "LiveTestStatus",
    "RepairStatus",
    "StatusReason",
    "StatusSection",
    "format_computer_use_status_markdown",
    "format_status_markdown",
]
