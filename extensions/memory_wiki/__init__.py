"""memory_wiki — JARVIS persistent wiki compiler + Obsidian-friendly vault.

OpenClaw parity: this is the Phase 4.3a foundation
scaffold. The plugin entry point is provided by
``index.py`` (Phase 4.3g) which calls
``register_memory_wiki(api)``. Phase 4.3a ships the
type / time / log / source-path / vault-page-write
primitives so subsequent sub-phases can build on a
shared surface.

This file is intentionally slim: it just re-exports
the public foundation surface for the host's
``extensions.memory_wiki`` import and registers the
plugin via ``define_plugin_entry`` so the host can
load it. The full ``register`` callback (with the
gateway methods, tool registrations, prompt section,
and lifecycle service) is wired in Phase 4.3g.
"""

from __future__ import annotations

import logging
from typing import Any

from jarvis_sdk import PluginApi, define_plugin_entry

from . import (
    config as _config,
    config_compat as _config_compat,
    log as _log,
    markdown as _markdown,
    source_path_shared as _source_path_shared,
    time as _time,
    vault as _vault,
    vault_page_write as _vault_page_write,
)

_LOGGER = logging.getLogger("jarvis.extensions.memory_wiki")


def register_memory_wiki(api: PluginApi) -> None:
    """Register the memory-wiki plugin with the host.

    Phase 4.3a ships a minimal registration: log a
    startup line so operators can see the plugin
    loaded, and surface the foundation helpers
    through ``api.runtime`` (so other sub-phases
    can call them without an import cycle). The
    full registration (gateway methods, tool
    registrations, prompt section, lifecycle
    service) is wired in Phase 4.3g.
    """
    logger = getattr(api, "logger", None)
    log_fn = getattr(logger, "info", None) if logger is not None else None
    if callable(log_fn):
        log_fn("memory-wiki: phase 4.3a foundation loaded")
    # Phase 4.3a does not register any service or
    # tool yet. Subsequent sub-phases will add:
    #   - register_service for the compiled-cache
    #     lifecycle (Phase 4.3e)
    #   - register_tool for the 5 wiki tools
    #     (Phase 4.3f)
    #   - register_cli for the ``wiki`` command
    #     (Phase 4.3g)


# ``define_plugin_entry`` is the SDK helper that
# builds the ``.entry`` symbol the host looks for
# when it imports the extension. The Phase 4.3a
# entry exposes a minimal registration callback;
# Phase 4.3g will replace it with the full surface.
entry = define_plugin_entry(
    id="memory_wiki",
    kind="memory",
    name="Memory Wiki",
    description=("Persistent wiki compiler and Obsidian-friendly " "knowledge vault for JARVIS."),
    activation="on_startup",
    register=register_memory_wiki,
)


# Public re-exports (the ``extensions.memory_wiki``
# surface that other extensions / tests can import).
__all__ = [
    "entry",
    "register_memory_wiki",
    # Foundation surface re-exported so callers can
    # ``from extensions.memory_wiki import resolve_artifact_key``
    # without reaching into the submodules.
    "resolve_artifact_key",
    "resolve_memory_wiki_timestamp",
    "append_memory_wiki_log",
    "ensure_memory_wiki_vault_generation",
    "load_memory_wiki_vault_identity",
    "load_memory_wiki_validated_vault_identity",
    "resolve_memory_wiki_vault_source_generation",
    "write_guarded_vault_page",
    # Config surface (Phase 4.3b).
    "memory_wiki_config_schema",
    "resolve_memory_wiki_config",
    "resolve_memory_wiki_agent_config",
    "resolve_memory_wiki_configured_agent_ids",
    "normalize_compatibility_config",
    # Vault init (Phase 4.3c).
    "initialize_memory_wiki_vault",
    "InitializeMemoryWikiVaultResult",
    "WIKI_VAULT_DIRECTORIES",
    "WIKI_VAULT_SCAFFOLD",
    # Markdown foundation (Phase 4.3c).
    "WIKI_PAGE_KINDS",
    "WIKI_RAW_SOURCE_MARKER",
    "WIKI_RELATED_START_MARKER",
    "WIKI_RELATED_END_MARKER",
    "parse_wiki_frontmatter",
    "replace_managed_markdown_block",
    "with_trailing_newline",
]


def resolve_artifact_key(absolute_path: str) -> str:
    """Re-export of :func:`.source_path_shared.resolve_artifact_key`."""
    return _source_path_shared.resolve_artifact_key(absolute_path)


def resolve_memory_wiki_timestamp(now_ms: int | float | None = None) -> str:
    """Re-export of :func:`.time.resolve_memory_wiki_timestamp`."""
    return _time.resolve_memory_wiki_timestamp(now_ms)


def append_memory_wiki_log(vault_root: str, entry: dict[str, Any]) -> None:
    """Re-export of :func:`.log.append_memory_wiki_log`."""
    return _log.append_memory_wiki_log(vault_root, entry)


def ensure_memory_wiki_vault_generation(vault_root: str) -> str:
    """Re-export of :func:`.log.ensure_memory_wiki_vault_generation`."""
    return _log.ensure_memory_wiki_vault_generation(vault_root)


def load_memory_wiki_vault_identity(vault_root: str):
    """Re-export of :func:`.log.load_memory_wiki_vault_identity`."""
    return _log.load_memory_wiki_vault_identity(vault_root)


def load_memory_wiki_validated_vault_identity(vault_root: str):
    """Re-export of :func:`.log.load_memory_wiki_validated_vault_identity`."""
    return _log.load_memory_wiki_validated_vault_identity(vault_root)


def resolve_memory_wiki_vault_source_generation(vault_root: str) -> str:
    """Re-export of :func:`.log.resolve_memory_wiki_vault_source_generation`."""
    return _log.resolve_memory_wiki_vault_source_generation(vault_root)


async def write_guarded_vault_page(**kwargs: Any) -> None:
    """Re-export of :func:`.vault_page_write.write_guarded_vault_page`."""
    await _vault_page_write.write_guarded_vault_page(**kwargs)


# Config re-exports so callers can do
# ``from extensions.memory_wiki import memory_wiki_config_schema``.
memory_wiki_config_schema = _config.memory_wiki_config_schema


def resolve_memory_wiki_config(config: Any, **kwargs: Any):
    """Re-export of :func:`.config.resolve_memory_wiki_config`."""
    return _config.resolve_memory_wiki_config(config, **kwargs)


def resolve_memory_wiki_agent_config(**kwargs: Any):
    """Re-export of :func:`.config.resolve_memory_wiki_agent_config`."""
    return _config.resolve_memory_wiki_agent_config(**kwargs)


def resolve_memory_wiki_configured_agent_ids(app_config: Any) -> list[str]:
    """Re-export of :func:`.config.resolve_memory_wiki_configured_agent_ids`."""
    return _config.resolve_memory_wiki_configured_agent_ids(app_config)


def normalize_compatibility_config(*, cfg: dict[str, Any]) -> dict[str, Any]:
    """Re-export of :func:`.config_compat.normalize_compatibility_config`."""
    return _config_compat.normalize_compatibility_config(cfg=cfg)


# Vault init (Phase 4.3c).
WIKI_VAULT_DIRECTORIES = _vault.WIKI_VAULT_DIRECTORIES
WIKI_VAULT_SCAFFOLD = _vault.WIKI_VAULT_SCAFFOLD
InitializeMemoryWikiVaultResult = _vault.InitializeMemoryWikiVaultResult


def initialize_memory_wiki_vault(config: Any, **kwargs: Any):
    """Re-export of :func:`.vault.initialize_memory_wiki_vault`."""
    return _vault.initialize_memory_wiki_vault(config, **kwargs)


# Markdown foundation (Phase 4.3c).
WIKI_PAGE_KINDS = _markdown.WIKI_PAGE_KINDS
WIKI_RAW_SOURCE_MARKER = _markdown.WIKI_RAW_SOURCE_MARKER
WIKI_RELATED_START_MARKER = _markdown.WIKI_RELATED_START_MARKER
WIKI_RELATED_END_MARKER = _markdown.WIKI_RELATED_END_MARKER
parse_wiki_frontmatter = _markdown.parse_wiki_frontmatter
replace_managed_markdown_block = _markdown.replace_managed_markdown_block
with_trailing_newline = _markdown.with_trailing_newline
