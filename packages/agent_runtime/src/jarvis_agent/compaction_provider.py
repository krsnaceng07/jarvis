"""Compaction provider registry — process-global singleton.

Port of ``src/plugins/compaction-provider.ts``.

Plugins implement the ``CompactionProvider`` protocol and register via
``register_compaction_provider()``.  The compaction safeguard checks this
registry before falling back to the built-in ``summarize_in_stages()``
pipeline.

The registry is a process-global module-level dict, mirroring the TS
``Symbol.for("openclaw.compactionProviderRegistryState")`` globalThis slot.
Duplicate dist-chunk safety (TS motivation) maps to Python's single module
namespace, so a plain module-level dict is the correct equivalent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------


@runtime_checkable
class CompactionProvider(Protocol):
    """A pluggable compaction provider that can replace the built-in pipeline.

    Parity: ``CompactionProvider`` interface from ``compaction-provider.ts``.
    """

    #: Unique provider id used for config lookup.
    id: str
    #: Human-readable label for logging and UI.
    label: str

    async def summarize(
        self,
        *,
        messages: list[Any],
        signal: Any | None = None,
        compression_ratio: float | None = None,
        custom_instructions: str | None = None,
        summarization_instructions: dict[str, Any] | None = None,
        previous_summary: str | None = None,
    ) -> str:
        """Summarize the given message list into a compact string.

        Args:
            messages: The messages to summarize (sanitized — no details).
            signal: Optional cancellation signal (asyncio.Event or similar).
            compression_ratio: Optional hint about desired compression level.
            custom_instructions: Optional caller-supplied focus instructions.
            summarization_instructions: Optional ``{identifierPolicy, ...}``.
            previous_summary: Summary from a prior compaction round, if any.

        Returns:
            Compaction summary text.
        """
        ...


# ---------------------------------------------------------------------------
# Registry entry
# ---------------------------------------------------------------------------


@dataclass
class RegisteredCompactionProvider:
    """A compaction provider with its owning plugin id for lifecycle tracking.

    Parity: ``RegisteredCompactionProvider`` (private type in TS source).
    """

    provider: CompactionProvider
    owner_plugin_id: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Process-global registry state
# ---------------------------------------------------------------------------

# Module-level dict — equivalent to the TS Symbol.for globalThis slot.
# One Python process = one module namespace = no duplicate-dist-chunk risk.
_REGISTRY: dict[str, RegisteredCompactionProvider] = {}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_compaction_provider(
    provider: CompactionProvider,
    owner_plugin_id: str | None = None,
) -> None:
    """Register a compaction provider implementation.

    Pass *owner_plugin_id* so the loader can snapshot/restore correctly.
    Parity: ``registerCompactionProvider``.
    """
    _REGISTRY[provider.id] = RegisteredCompactionProvider(
        provider=provider,
        owner_plugin_id=owner_plugin_id,
    )


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


def get_compaction_provider(provider_id: str) -> CompactionProvider | None:
    """Return the provider for the given id, or ``None``.

    Parity: ``getCompactionProvider``.
    """
    entry = _REGISTRY.get(provider_id)
    return entry.provider if entry is not None else None


def get_registered_compaction_provider(
    provider_id: str,
) -> RegisteredCompactionProvider | None:
    """Return the registered entry (provider + owner) for the given id.

    Parity: ``getRegisteredCompactionProvider``.
    """
    return _REGISTRY.get(provider_id)


def list_registered_compaction_providers() -> list[RegisteredCompactionProvider]:
    """List all registered entries with owner metadata.

    Used for plugin snapshot/restore.
    Parity: ``listRegisteredCompactionProviders``.
    """
    return list(_REGISTRY.values())


# ---------------------------------------------------------------------------
# Lifecycle (clear / restore) — mirrors memory-embedding-providers pattern
# ---------------------------------------------------------------------------


def clear_compaction_providers() -> None:
    """Clear all compaction providers.

    Called by ``clearPluginLoaderCache()`` and plugin reload.
    Parity: ``clearCompactionProviders``.
    """
    _REGISTRY.clear()


def restore_registered_compaction_providers(
    entries: list[RegisteredCompactionProvider],
) -> None:
    """Restore from a snapshot, replacing all current entries.

    Parity: ``restoreRegisteredCompactionProviders``.
    """
    _REGISTRY.clear()
    for entry in entries:
        _REGISTRY[entry.provider.id] = entry


__all__ = [
    "CompactionProvider",
    "RegisteredCompactionProvider",
    "clear_compaction_providers",
    "get_compaction_provider",
    "get_registered_compaction_provider",
    "list_registered_compaction_providers",
    "register_compaction_provider",
    "restore_registered_compaction_providers",
]
