"""JARVIS Vault infra extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import VaultPlugin, vault_plugin, entry

__all__ = [
    "VaultPlugin",
    "vault_plugin",
    "entry",
]
