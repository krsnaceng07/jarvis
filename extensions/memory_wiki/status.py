"""status — Memory Wiki status report (Phase 4.3f-mr3 stub).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/status.ts``.

The full status implementation (which walks
the vault + the compiled cache + the
Obsidian CLI availability + the active
agent count) lands in Phase 4.3g. Phase
4.3f-mr3 ships the
:func:`resolve_memory_wiki_status` +
:func:`render_memory_wiki_status` stubs so
the ``wiki_status`` tool surface is fully
wired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


@dataclass
class MemoryWikiStatus:
    """The status payload returned by :func:`resolve_memory_wiki_status`.

    Mirrors the OpenClaw ``MemoryWikiStatus``
    shape (the deep checks are added in
    4.3g).
    """

    vault_path: str
    vault_mode: str
    render_mode: str = "native"
    obsidian_cli_available: bool = False
    unsafe_local_path: str | None = None
    bridge_enabled: bool = False
    agent_ids: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def resolve_memory_wiki_status(
    config: ResolvedMemoryWikiConfig,
    *,
    caller_agent_id: str | None = None,
) -> MemoryWikiStatus:
    """Resolve the current vault status (Phase 4.3f-mr3 stub).

    Returns a minimal ``MemoryWikiStatus``
    populated from the config. The full
    implementation lands in Phase 4.3g.
    """
    return MemoryWikiStatus(
        vault_path=str(config.vault.path),
        vault_mode=str(getattr(config, "vaultMode", "single")),
        render_mode=str(getattr(config.vault, "renderMode", "native")),
        bridge_enabled=bool(getattr(config.bridge, "enabled", False)),
        agent_ids=[caller_agent_id] if caller_agent_id else [],
    )


def render_memory_wiki_status(status: MemoryWikiStatus) -> str:
    """Render ``status`` as plain text.

    Mirrors the OpenClaw
    ``renderMemoryWikiStatus`` (a simplified
    version: a single ``key: value`` block
    so the tool layer can show the status
    immediately).
    """
    lines = [
        f"Vault mode: {status.vault_mode}",
        f"Render mode: {status.render_mode}",
        f"Vault path: {status.vault_path}",
        f"Bridge enabled: {status.bridge_enabled}",
        f"Obsidian CLI available: {status.obsidian_cli_available}",
    ]
    if status.unsafe_local_path:
        lines.append(f"Unsafe local path: {status.unsafe_local_path}")
    if status.agent_ids:
        lines.append(f"Active agents: {', '.join(status.agent_ids)}")
    return "\n".join(lines)


def reset_memory_wiki_status_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


__all__ = [
    "MemoryWikiStatus",
    "render_memory_wiki_status",
    "reset_memory_wiki_status_state_for_tests",
    "resolve_memory_wiki_status",
]
