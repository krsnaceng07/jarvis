"""Codex remote-exec placement sandbox predicates.

OpenClaw parity: mirrors ``isCodexRemoteExecPlacementSandbox`` and
``isCodexPairedNodeRemoteExecPlacementSandbox`` from
``openclaw-main/extensions/codex/src/app-server/config-parsing.ts``.

Prompt routing follows the selected runtime *and* placement, not just the
provider string: a paired-device ``remote-exec`` sandbox disables ``/btw``
side questions (see ``extensions/codex/src/commands.py``), while other
placements keep them.
"""

from __future__ import annotations

from typing import Any


def is_remote_exec_placement_sandbox(sandbox: Any) -> bool:
    """Return whether *sandbox* is a remote-exec placement.

    Mirrors ``isCodexRemoteExecPlacementSandbox``.
    """
    return isinstance(sandbox, dict) and sandbox.get("placementExecutionMode") == "remote-exec"


def is_paired_node_remote_exec_placement_sandbox(sandbox: Any) -> bool:
    """Return whether *sandbox* is a paired-device remote-exec placement.

    Mirrors ``isCodexPairedNodeRemoteExecPlacementSandbox``: remote-exec
    *plus* a non-empty ``placementNodeId``. Cloud/implicit remote-exec
    without a paired node id does not match.
    """
    if not is_remote_exec_placement_sandbox(sandbox):
        return False
    if not isinstance(sandbox, dict):
        return False
    node_id = sandbox.get("placementNodeId")
    return isinstance(node_id, str) and len(node_id) > 0


def _read_sandbox_exec_server_flag(plugin_config: Any) -> bool:
    """Read ``appServer.experimental.sandbox_exec_server`` from a plugin
    config dict or ``CodexPluginConfig`` dataclass."""
    app_server = None
    if isinstance(plugin_config, dict):
        app_server = plugin_config.get("appServer", plugin_config.get("app_server"))
    else:
        app_server = getattr(plugin_config, "app_server", getattr(plugin_config, "appServer", None))
    if isinstance(app_server, dict):
        experimental = app_server.get("experimental")
    else:
        experimental = getattr(app_server, "experimental", None)
    if isinstance(experimental, dict):
        return experimental.get("sandbox_exec_server") is True
    return getattr(experimental, "sandbox_exec_server", None) is True


def is_codex_sandbox_exec_server_enabled(plugin_config: Any = None, sandbox: Any = None) -> bool:
    """Return whether the Codex sandbox exec-server path is enabled.

    Mirrors ``isCodexSandboxExecServerEnabled``: a remote-exec placement
    sandbox enables it, otherwise the plugin config's experimental
    ``sandbox_exec_server`` flag decides.
    """
    return is_remote_exec_placement_sandbox(sandbox) or _read_sandbox_exec_server_flag(
        plugin_config
    )


__all__ = [
    "is_codex_sandbox_exec_server_enabled",
    "is_paired_node_remote_exec_placement_sandbox",
    "is_remote_exec_placement_sandbox",
]
