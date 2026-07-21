"""types — data shapes for the memory-wiki extension.

OpenClaw parity: this file is a Phase 4.3a stub. The full
type surface ships in Phase 4.3b (config types) +
Phase 4.3c (markdown frontmatter / page types) +
Phase 4.3d (compile types). The minimal types here are
just enough for the foundation: log entry, vault
identity, and a placeholder for the resolved config
that ``log.py`` and ``time.py`` consume.
"""

from __future__ import annotations

from typing import Any, Literal

# Mirror OpenClaw's ``type`` union on the log entries.
# Phase 4.3a only writes ``vault-generation``; the
# remaining types land in later sub-phases.
MemoryWikiLogEntryType = Literal[
    "init",
    "vault-generation",
    "ingest",
    "okf-import",
    "compile",
    "lint",
]


class MemoryWikiVaultIdentity(dict[str, Any]):
    """Lightweight identity for the memory-wiki vault.

    Mirrors OpenClaw's ``MemoryWikiVaultIdentity``
    return type from ``loadMemoryWikiVaultIdentity``.

    The Python port uses a plain ``dict`` so callers can
    pattern-match with the OpenClaw field names
    (``vaultGeneration``, ``compiledCacheReservationId``,
    ``compiledCachePublicationId``,
    ``compiledCacheSourceGeneration``) without a custom
    dataclass ceremony. The fields default to ``None``
    on a fresh vault.
    """

    def __init__(
        self,
        *,
        vault_generation: str | None = None,
        compiled_cache_reservation_id: str | None = None,
        compiled_cache_publication_id: str | None = None,
        compiled_cache_source_generation: str | None = None,
    ) -> None:
        super().__init__(
            vaultGeneration=vault_generation,
            compiledCacheReservationId=compiled_cache_reservation_id,
            compiledCachePublicationId=compiled_cache_publication_id,
            compiledCacheSourceGeneration=compiled_cache_source_generation,
        )

    # Convenience read accessors so callers can stay in
    # snake_case without losing the OpenClaw field names
    # on serialization.
    @property
    def vault_generation(self) -> str | None:
        return self.get("vaultGeneration")

    @property
    def compiled_cache_reservation_id(self) -> str | None:
        return self.get("compiledCacheReservationId")

    @property
    def compiled_cache_publication_id(self) -> str | None:
        return self.get("compiledCachePublicationId")

    @property
    def compiled_cache_source_generation(self) -> str | None:
        return self.get("compiledCacheSourceGeneration")


__all__ = [
    "MemoryWikiLogEntryType",
    "MemoryWikiVaultIdentity",
]
