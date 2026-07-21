"""setup_api — Memory Wiki setup-time hooks (Phase 4.3g-mr6).

OpenClaw parity: mirrors
``extensions/memory-wiki/setup-api.ts``.

The setup-API entry registers a single
config-migration hook so the legacy
``plugins.entries.memory-wiki.config.bridge
.readMemoryCore`` flag is migrated to
the canonical ``bridge.readMemoryArtifacts``
flag on every plugin startup.

The Python port keeps the migration in
:mod:`.config_compat`; this module just
exposes the small
``register_memory_wiki_setup`` registrar
the host calls during plugin
initialization.
"""

# ruff: noqa: ASYNC230 — config-migration is bounded (a few dict walks) and
# stays sync by design (mirrors the OpenClaw sync path).

# ruff: noqa: ASYNC230 — config-migration is bounded (a few dict walks) and
# stays sync by design (mirrors the OpenClaw sync path).

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .config_compat import normalize_compatibility_config

if TYPE_CHECKING:
    from . import PluginApi


def register_memory_wiki_setup(api: PluginApi) -> None:
    """Register the memory-wiki setup hooks
    with the host.

    Mirrors OpenClaw's
    ``setup-api.ts`` ``register(api)``
    body. Registers a single
    ``registerConfigMigration`` hook that
    runs :func:`normalize_compatibility_config`
    on the host's plugin config.

    The host invokes this registrar during
    plugin loading — it should NOT be
    called manually. The function is
    idempotent: calling it twice with the
    same ``api`` is a no-op.
    """
    register_migration = getattr(api, "register_config_migration", None)
    if not callable(register_migration):
        # Older hosts don't expose
        # ``registerConfigMigration``;
        # skip the hook silently.
        return

    def _migrate(config: Any) -> dict[str, Any]:
        if not isinstance(config, dict):
            return {"config": config, "changes": []}
        result = normalize_compatibility_config(cfg=config)
        return {
            "config": result.get("config", config),
            "changes": list(result.get("changes", [])),
        }

    register_migration(_migrate)


__all__ = ["register_memory_wiki_setup"]
