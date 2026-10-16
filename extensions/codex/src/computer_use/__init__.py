"""Codex Computer Use — JARVIS port of OpenClaw's computer-use contract.

OpenClaw parity: ``extensions/codex/src/app-server/computer-use.ts``.

Three public entry points, matching OpenClaw verbatim:
- ``read_status``   — pure status probe (no mutation).
- ``ensure_ready``  — install when ``autoInstall`` is set and not yet ready.
- ``install``       — forced install regardless of current config.
"""

from .config import (
    CodexComputerUseConfig,
    ResolvedCodexComputerUseConfig,
    resolve_computer_use_config,
)
from .service import (
    CodexComputerUseSetupError,
    ensure_ready,
    install,
    read_status,
    run_live_test,
)
from .status import (
    CodexComputerUseStatus,
    InstallationStatus,
    LiveTestStatus,
    StatusSection,
)

__all__ = [
    # config
    "CodexComputerUseConfig",
    "ResolvedCodexComputerUseConfig",
    "resolve_computer_use_config",
    # service
    "CodexComputerUseSetupError",
    "ensure_ready",
    "install",
    "read_status",
    "run_live_test",
    # status
    "CodexComputerUseStatus",
    "InstallationStatus",
    "LiveTestStatus",
    "StatusSection",
]
