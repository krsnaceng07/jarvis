"""compiled_cache — Memory Wiki compiled cache ownership and persistence.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/compiled-cache.ts``.

The compiled cache is the immutable
publish-once digest + per-claim projections
that the memory-wiki compile pipeline writes
after every scan. Each publication is
identified by a UUID ``publicationId`` and
keyed by a SHA-256 hash of the owner id
(``"global"`` for the global vault scope;
``"agent:<agentId>"`` for agent-scoped
vaults).

Phase 4.3e-mr3 ships the in-memory + file
blob store, the active-vault tracking, the
causal publication chain, and the public
``load`` / ``invalidate`` / ``reconcile`` /
``write`` helpers. The full SQLite-backed
plugin-blob-store variant lives in the SDK
and is used when a namespace root is
configured.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from .config import ResolvedMemoryWikiConfig


# Mirrors the OpenClaw
# ``LEGACY_MEMORY_WIKI_COMPILED_CACHE_PATHS``
# + the namespace + cap constants.
LEGACY_MEMORY_WIKI_COMPILED_CACHE_PATHS: tuple[str, ...] = (
    ".openclaw-wiki/cache/agent-digest.json",
    ".openclaw-wiki/cache/claims.jsonl",
)

COMPILED_CACHE_NAMESPACE = "compiled-cache"
COMPILED_CACHE_MAX_ENTRIES = 256
COMPILED_CACHE_MAX_BYTES_PER_ENTRY = 100 * 1024 * 1024
COMPILED_CACHE_MAX_BYTES = 512 * 1024 * 1024
COMPILED_CACHE_VERSION = 2


# ── snapshot types ────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MemoryWikiCompiledDigestClaim:
    """One digest-claim row. Mirrors the OpenClaw ``MemoryWikiCompiledDigestClaim`` shape."""

    text: str
    status: str
    freshness_level: str
    id: str | None = None
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class MemoryWikiCompiledDigestPage:
    """One digest-page row. Mirrors the OpenClaw ``MemoryWikiCompiledDigestPage`` shape."""

    title: str
    kind: str
    path: str
    aliases: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    best_used_for: list[str] = field(default_factory=list)
    not_enough_for: list[str] = field(default_factory=list)
    relationship_count: int = 0
    top_relationships: list[dict[str, Any]] = field(default_factory=list)
    claim_count: int = 0
    top_claims: list[MemoryWikiCompiledDigestClaim] = field(default_factory=list)
    id: str | None = None
    page_type: str | None = None
    entity_type: str | None = None
    canonical_id: str | None = None
    privacy_tier: str | None = None
    person_card: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class MemoryWikiCompiledClaim:
    """One projected claim row. Mirrors the OpenClaw ``MemoryWikiCompiledClaim`` shape."""

    page_title: str
    page_kind: str
    page_path: str
    text: str
    id: str | None = None
    page_id: str | None = None
    page_type: str | None = None
    entity_type: str | None = None
    canonical_id: str | None = None
    aliases: list[str] | None = None
    status: str | None = None
    confidence: float | None = None
    source_ids: list[str] | None = None
    evidence_kinds: list[str] | None = None
    privacy_tiers: list[str] | None = None
    freshness_level: str | None = None
    last_touched_at: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryWikiCompiledCacheSnapshot:
    """The compiled cache payload. Mirrors the OpenClaw ``MemoryWikiCompiledCacheSnapshot`` shape.

    The ``digest`` is the per-page projection
    used by the prompt section; ``claims``
    is the per-claim projection used by the
    query / corpus pipelines.
    """

    digest: dict[str, Any]
    claims: list[MemoryWikiCompiledClaim] = field(default_factory=list)


# ── blob store ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CompiledCacheMetadata:
    """Per-entry metadata stored alongside the gzip payload.

    Mirrors OpenClaw's
    ``CompiledCacheMetadata``.
    """

    version: int
    owner_id: str
    vault_path: str
    vault_generation: str
    publication_id: str
    generation: str
    encoding: str = "gzip-json"


@dataclass(frozen=True, slots=True)
class CompiledCacheEntry:
    """The blob-store row shape (key + bytes + metadata)."""

    key: str
    bytes: bytes
    metadata: CompiledCacheMetadata


class CompiledCacheBlobStore:
    """The in-memory compiled-cache blob store.

    Mirrors the OpenClaw ``PluginBlobStore``
    surface (``lookup`` / ``register`` /
    ``entries`` / ``delete``). Uses an
    in-memory dict for the tests; the
    production SQLite-backed variant lives
    in the SDK and is wired in by the host.
    """

    def __init__(self) -> None:
        self._entries: dict[str, CompiledCacheEntry] = {}

    def register(
        self,
        key: str,
        payload: bytes,
        metadata: CompiledCacheMetadata,
    ) -> None:
        self._entries[key] = CompiledCacheEntry(key=key, bytes=payload, metadata=metadata)
        # Enforce the cap: drop the oldest
        # entry when we exceed
        # ``COMPILED_CACHE_MAX_ENTRIES``.
        if len(self._entries) > COMPILED_CACHE_MAX_ENTRIES:
            oldest_key = next(iter(self._entries))
            self._entries.pop(oldest_key, None)

    def lookup(self, key: str) -> CompiledCacheEntry | None:
        return self._entries.get(key)

    def entries(self) -> list[CompiledCacheEntry]:
        return list(self._entries.values())

    def delete(self, key: str) -> bool:
        return self._entries.pop(key, None) is not None

    def clear(self) -> None:
        self._entries.clear()


# ── active vault tracking ─────────────────────────────────


@dataclass(frozen=True, slots=True)
class ActiveVault:
    """The in-memory active-vault record.

    Mirrors the OpenClaw ``ActiveVault``
    shape. ``reconciled`` is False until
    :func:`reconcile_memory_wiki_compiled_cache_owner`
    confirms the durable identity.
    """

    path: str
    vault_generation: str
    compiled_cache_publication_id: str | None = None
    reconciled: bool = False


# Module-level active vault map. Mirrors
# OpenClaw's ``activeVaults`` map.
_active_vaults: dict[str, ActiveVault] = {}

# Module-level configured store. Mirrors
# OpenClaw's ``configuredStore``.
_configured_store: MemoryWikiCompiledCacheStore | None = None


# ── owner + key helpers ───────────────────────────────────


def resolve_memory_wiki_compiled_cache_owner_id(
    config: ResolvedMemoryWikiConfig,
) -> str:
    """Return the owner id for ``config``.

    Mirrors OpenClaw's
    ``resolveMemoryWikiCompiledCacheOwnerId``.
    Global scope → ``"global"``; agent scope
    → ``"agent:<agentId>"``.
    """
    if config.vault.scope == "global":
        return "global"
    agent_id = config.agent_id
    if agent_id is None:
        agent_id_str: str | None = None
    else:
        agent_id_str = agent_id.strip() if isinstance(agent_id, str) else None
    if not agent_id_str:
        raise ValueError("Memory Wiki agent-scoped compiled cache requires an agent owner.")
    return f"agent:{agent_id_str}"


def _owner_key_prefix(owner_id: str) -> str:
    """Return the owner-key prefix used in the publication key.

    Mirrors OpenClaw's ``ownerKeyPrefix``:
    SHA-256 of the owner id, formatted as
    ``"owner:<hex>:publication:"``.
    """
    hex_digest = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()
    return f"owner:{hex_digest}:publication:"


def _publication_key(owner_id: str, publication_id: str) -> str:
    """Return the full publication key.

    Mirrors OpenClaw's ``publicationKey``.
    """
    return (
        f"{_owner_key_prefix(owner_id)}"
        f"{hashlib.sha256(publication_id.encode('utf-8')).hexdigest()}"
    )


def resolve_memory_wiki_compiled_cache_generation(
    snapshot: MemoryWikiCompiledCacheSnapshot,
) -> str:
    """Return the SHA-256 generation hash for ``snapshot``.

    Mirrors OpenClaw's
    ``resolveMemoryWikiCompiledCacheGeneration``.
    """
    serialized = json.dumps(_snapshot_to_dict(snapshot), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def create_memory_wiki_compiled_cache_publication_id() -> str:
    """Return a new UUID publication id.

    Mirrors OpenClaw's
    ``createMemoryWikiCompiledCachePublicationId``.
    """
    return str(uuid.uuid4())


# ── active vault helpers ──────────────────────────────────


def activate_memory_wiki_compiled_cache_owner(
    config: ResolvedMemoryWikiConfig,
    vault_generation: str,
    compiled_cache_publication_id: str | None = None,
) -> None:
    """Activate the compiled-cache owner for ``config``.

    Mirrors OpenClaw's
    ``activateMemoryWikiCompiledCacheOwner``.
    The vault generation must be non-empty.
    """
    if not vault_generation or not vault_generation.strip():
        raise ValueError("Memory Wiki vault generation must not be empty.")
    owner_id = resolve_memory_wiki_compiled_cache_owner_id(config)
    normalized = vault_generation.strip()
    normalized_publication_id: str | None = None
    if compiled_cache_publication_id is not None:
        trimmed = compiled_cache_publication_id.strip()
        if trimmed:
            normalized_publication_id = trimmed
    _active_vaults[owner_id] = ActiveVault(
        path=os.path.abspath(config.vault.path),
        vault_generation=normalized,
        compiled_cache_publication_id=normalized_publication_id,
        reconciled=False,
    )


def deactivate_memory_wiki_compiled_cache_owners_except(
    owner_ids: set[str],
) -> None:
    """Drop every active owner not in ``owner_ids``.

    Mirrors OpenClaw's
    ``deactivateMemoryWikiCompiledCacheOwnersExcept``.
    """
    for owner_id in list(_active_vaults):
        if owner_id not in owner_ids:
            _active_vaults.pop(owner_id, None)


def _resolve_active_vault(
    config: ResolvedMemoryWikiConfig,
) -> ActiveVault | None:
    """Return the active vault for ``config`` (or ``None``)."""
    owner_id = resolve_memory_wiki_compiled_cache_owner_id(config)
    active = _active_vaults.get(owner_id)
    if active is None:
        return None
    if active.path != os.path.abspath(config.vault.path):
        return None
    return active


# ── public store API ──────────────────────────────────────


@dataclass
class MemoryWikiCompiledCacheStore:
    """The compiled-cache store API.

    Mirrors the OpenClaw
    ``MemoryWikiCompiledCacheStore`` shape.
    The store is built by
    :func:`create_memory_wiki_compiled_cache_store`
    and exposes ``read`` / ``write`` /
    ``reconcile`` / ``delete`` /
    ``delete_publication`` /
    ``delete_owners_except`` methods.
    """

    blob_store: CompiledCacheBlobStore = field(default_factory=CompiledCacheBlobStore)

    def read(
        self,
        config: ResolvedMemoryWikiConfig,
    ) -> MemoryWikiCompiledCacheSnapshot | None:
        """Read the compiled cache for ``config``.

        Mirrors OpenClaw's ``store.read``.
        Returns ``None`` when the vault is
        not active, not reconciled, or has no
        publication id; or when the stored
        metadata doesn't match the current
        vault state (stale row).
        """
        owner_id = resolve_memory_wiki_compiled_cache_owner_id(config)
        active_vault = _resolve_active_vault(config)
        if (
            active_vault is None
            or not active_vault.reconciled
            or not active_vault.compiled_cache_publication_id
        ):
            return None
        key = _publication_key(owner_id, active_vault.compiled_cache_publication_id)
        entry = self.blob_store.lookup(key)
        if entry is None:
            return None
        if (
            entry.metadata.owner_id != owner_id
            or entry.metadata.vault_path != os.path.abspath(config.vault.path)
            or entry.metadata.vault_generation != active_vault.vault_generation
            or entry.metadata.publication_id != active_vault.compiled_cache_publication_id
        ):
            return None
        return _parse_snapshot_payload(entry.bytes, entry.metadata.generation)

    def write(
        self,
        config: ResolvedMemoryWikiConfig,
        snapshot: MemoryWikiCompiledCacheSnapshot,
        generation: str,
        publication_id: str,
    ) -> ActiveVault:
        """Persist a compiled-cache snapshot.

        Mirrors OpenClaw's ``store.write``.
        Raises if the vault is not active, or
        if the supplied ``generation`` doesn't
        match the snapshot's actual hash.
        """
        owner_id = resolve_memory_wiki_compiled_cache_owner_id(config)
        vault_path = os.path.abspath(config.vault.path)
        active_vault = _resolve_active_vault(config)
        if active_vault is None:
            raise ValueError(f"Memory Wiki vault is not active: {vault_path}")
        actual_generation = resolve_memory_wiki_compiled_cache_generation(snapshot)
        if actual_generation != generation:
            raise ValueError("Memory Wiki compiled cache generation does not match its snapshot.")
        metadata = CompiledCacheMetadata(
            version=COMPILED_CACHE_VERSION,
            owner_id=owner_id,
            vault_path=vault_path,
            vault_generation=active_vault.vault_generation,
            publication_id=publication_id,
            generation=generation,
        )
        # The generation hash is computed with
        # ``sort_keys=True`` (see
        # ``resolve_memory_wiki_compiled_cache_generation``)
        # so the wire encoding must use the
        # same key order, otherwise the
        # parse-on-read step rejects the
        # payload.
        serialized = json.dumps(
            _snapshot_to_dict(snapshot),
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        compressed = gzip.compress(serialized)
        self.blob_store.register(_publication_key(owner_id, publication_id), compressed, metadata)
        return active_vault

    def reconcile(
        self,
        config: ResolvedMemoryWikiConfig,
        load_durable_identity: Callable[[], dict[str, str | None]],
    ) -> None:
        """Reconcile the active vault with the durable identity.

        Mirrors OpenClaw's
        ``store.reconcile``. Confirms the
        durable identity, then marks the
        active vault ``reconciled``.
        """
        owner_id = resolve_memory_wiki_compiled_cache_owner_id(config)
        active_vault = _resolve_active_vault(config)
        if active_vault is None:
            return
        durable_identity = load_durable_identity()
        # The OpenClaw store calls
        # ``store.lookup`` here so the durable
        # row gets observed before the
        # identity is reread; the Python port
        # uses the in-memory blob store so the
        # equivalent is a single read.
        if durable_identity.get("compiledCachePublicationId"):
            try:
                self.blob_store.lookup(
                    _publication_key(
                        owner_id,
                        durable_identity["compiledCachePublicationId"] or "",
                    )
                )
            except Exception:
                raise
        confirmed_identity = load_durable_identity()
        if _resolve_active_vault(config) != active_vault:
            return
        if (
            not confirmed_identity.get("vaultGeneration")
            or confirmed_identity.get("vaultGeneration") != durable_identity.get("vaultGeneration")
            or confirmed_identity.get("compiledCachePublicationId")
            != durable_identity.get("compiledCachePublicationId")
        ):
            _active_vaults.pop(owner_id, None)
            return
        _active_vaults[owner_id] = ActiveVault(
            path=active_vault.path,
            vault_generation=confirmed_identity["vaultGeneration"] or "",
            compiled_cache_publication_id=confirmed_identity.get("compiledCachePublicationId"),
            reconciled=True,
        )

    def delete(self, config: ResolvedMemoryWikiConfig) -> None:
        """Delete every compiled-cache entry for ``config``.

        Mirrors OpenClaw's ``store.delete``.
        """
        owner_id = resolve_memory_wiki_compiled_cache_owner_id(config)
        for entry in self.blob_store.entries():
            if entry.metadata.owner_id == owner_id:
                self.blob_store.delete(entry.key)

    def delete_publication(self, config: ResolvedMemoryWikiConfig, publication_id: str) -> None:
        """Delete a single publication.

        Mirrors OpenClaw's
        ``store.deletePublication``.
        """
        owner_id = resolve_memory_wiki_compiled_cache_owner_id(config)
        self.blob_store.delete(_publication_key(owner_id, publication_id))

    def delete_owners_except(self, owner_ids: set[str]) -> int:
        """Delete every entry whose owner id is not in ``owner_ids``.

        Mirrors OpenClaw's
        ``store.deleteOwnersExcept``. Returns
        the number of entries deleted.
        """
        deleted = 0
        for entry in self.blob_store.entries():
            if entry.metadata.owner_id not in owner_ids:
                self.blob_store.delete(entry.key)
                deleted += 1
        return deleted


def create_memory_wiki_compiled_cache_store(
    blob_store: CompiledCacheBlobStore | None = None,
) -> MemoryWikiCompiledCacheStore:
    """Build a compiled-cache store.

    Mirrors OpenClaw's
    ``createMemoryWikiCompiledCacheStore``.
    The optional ``blob_store`` parameter
    accepts an explicit blob store (default:
    a fresh in-memory ``CompiledCacheBlobStore``).
    """
    if blob_store is None:
        blob_store = CompiledCacheBlobStore()
    return MemoryWikiCompiledCacheStore(blob_store=blob_store)


def configure_memory_wiki_compiled_cache_store(
    store: MemoryWikiCompiledCacheStore | None,
) -> None:
    """Configure the process-wide compiled-cache store.

    Mirrors OpenClaw's
    ``configureMemoryWikiCompiledCacheStore``.
    ``None`` resets to no store (the public
    ``load`` / ``write`` / ``reconcile``
    helpers raise when no store is
    configured).
    """
    global _configured_store  # noqa: PLW0603 — process-wide SDK config
    _configured_store = store
    if store is None:
        _active_vaults.clear()


def _require_configured_store() -> MemoryWikiCompiledCacheStore:
    if _configured_store is None:
        raise ValueError("Memory Wiki compiled cache store is not configured.")
    return _configured_store


def load_memory_wiki_compiled_cache(
    config: ResolvedMemoryWikiConfig,
) -> MemoryWikiCompiledCacheSnapshot | None:
    """Read the compiled cache for ``config`` via the configured store.

    Mirrors OpenClaw's
    ``loadMemoryWikiCompiledCache``.
    """
    return _require_configured_store().read(config)


def invalidate_memory_wiki_compiled_cache(
    config: ResolvedMemoryWikiConfig,
) -> None:
    """Drop every compiled-cache entry for ``config``.

    Mirrors OpenClaw's
    ``invalidateMemoryWikiCompiledCache``.
    """
    _require_configured_store().delete(config)


def reconcile_memory_wiki_compiled_cache_owner(
    config: ResolvedMemoryWikiConfig,
    load_durable_identity: Callable[[], dict[str, str | None]],
) -> None:
    """Reconcile the active owner with the durable identity.

    Mirrors OpenClaw's
    ``reconcileMemoryWikiCompiledCacheOwner``.
    """
    _require_configured_store().reconcile(config, load_durable_identity)


def write_memory_wiki_compiled_cache(
    config: ResolvedMemoryWikiConfig,
    snapshot: MemoryWikiCompiledCacheSnapshot,
    generation: str,
    publication_id: str,
    parent_publication_id: str | None,
    validate_publication: Callable[[], None],
    commit_publication: Callable[[], None],
    load_durable_identity: Callable[[], dict[str, str | None]],
) -> None:
    """Publish a compiled-cache snapshot.

    Mirrors OpenClaw's
    ``writeMemoryWikiCompiledCache``. The
    publish-then-validate-then-commit
    sequence preserves the causal
    publication chain: if validation fails,
    the publication is deleted; if commit
    fails, the publication is deleted
    (unless the durable identity has already
    accepted it).
    """
    store = _require_configured_store()
    active_vault = store.write(config, snapshot, generation, publication_id)
    try:
        validate_publication()
    except Exception:
        store.delete_publication(config, publication_id)
        raise
    try:
        commit_publication()
    except Exception:
        try:
            identity = load_durable_identity()
        except Exception:
            identity = None
        if identity is None or identity.get("compiledCachePublicationId") != publication_id:
            store.delete_publication(config, publication_id)
        raise
    durable_identity = load_durable_identity()
    if (
        durable_identity.get("vaultGeneration") != active_vault.vault_generation
        or durable_identity.get("compiledCachePublicationId") != publication_id
    ):
        store.delete_publication(config, publication_id)
        if _resolve_active_vault(config) == active_vault:
            owner_id = resolve_memory_wiki_compiled_cache_owner_id(config)
            _active_vaults.pop(owner_id, None)
        raise ValueError("Memory Wiki vault changed while its compiled cache was being published.")
    if parent_publication_id:
        store.delete_publication(config, parent_publication_id)
    if _resolve_active_vault(config) != active_vault:
        return
    owner_id = resolve_memory_wiki_compiled_cache_owner_id(config)
    _active_vaults[owner_id] = ActiveVault(
        path=active_vault.path,
        vault_generation=active_vault.vault_generation,
        compiled_cache_publication_id=publication_id,
        reconciled=True,
    )


# ── payload encoding ──────────────────────────────────────


def _parse_snapshot_payload(  # noqa: PLR0911 — mirrors OpenClaw's parseSnapshot
    payload: bytes,
    generation: str,
) -> MemoryWikiCompiledCacheSnapshot | None:
    """Decompress + parse + verify generation. Mirrors OpenClaw's ``parseSnapshot``."""
    try:
        serialized = gzip.decompress(payload).decode("utf-8")
    except (OSError, ValueError):
        return None
    if hashlib.sha256(serialized.encode("utf-8")).hexdigest() != generation:
        return None
    try:
        parsed: Any = json.loads(serialized)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    digest = parsed.get("digest")
    if not isinstance(digest, dict):
        return None
    pages = digest.get("pages")
    if not isinstance(pages, list):
        return None
    claims_raw = parsed.get("claims")
    if not isinstance(claims_raw, list):
        return None
    return _dict_to_snapshot(parsed)


def _snapshot_to_dict(
    snapshot: MemoryWikiCompiledCacheSnapshot,
) -> dict[str, Any]:
    """Serialize a snapshot to a JSON-friendly dict."""
    return {
        "digest": snapshot.digest,
        "claims": [_claim_to_dict(c) for c in snapshot.claims],
    }


def _claim_to_dict(claim: MemoryWikiCompiledClaim) -> dict[str, Any]:
    out: dict[str, Any] = {
        "pageTitle": claim.page_title,
        "pageKind": claim.page_kind,
        "pagePath": claim.page_path,
        "text": claim.text,
    }
    for k, v in (
        ("id", claim.id),
        ("pageId", claim.page_id),
        ("pageType", claim.page_type),
        ("entityType", claim.entity_type),
        ("canonicalId", claim.canonical_id),
        ("status", claim.status),
        ("confidence", claim.confidence),
        ("freshnessLevel", claim.freshness_level),
        ("lastTouchedAt", claim.last_touched_at),
    ):
        if v is not None:
            out[k] = v
    if claim.aliases is not None:
        out["aliases"] = claim.aliases
    if claim.source_ids is not None:
        out["sourceIds"] = claim.source_ids
    if claim.evidence_kinds is not None:
        out["evidenceKinds"] = claim.evidence_kinds
    if claim.privacy_tiers is not None:
        out["privacyTiers"] = claim.privacy_tiers
    return out


def _dict_to_snapshot(
    raw: dict[str, Any],
) -> MemoryWikiCompiledCacheSnapshot:
    """Deserialize a snapshot from a dict."""
    digest = raw.get("digest") if isinstance(raw.get("digest"), dict) else {}
    claims_raw = raw.get("claims", [])
    claims: list[MemoryWikiCompiledClaim] = []
    if isinstance(claims_raw, list):
        for c in claims_raw:
            if not isinstance(c, dict):
                continue
            claims.append(
                MemoryWikiCompiledClaim(
                    page_title=str(c.get("pageTitle", "")),
                    page_kind=str(c.get("pageKind", "")),
                    page_path=str(c.get("pagePath", "")),
                    text=str(c.get("text", "")),
                    id=c.get("id") if isinstance(c.get("id"), str) else None,
                    page_id=c.get("pageId") if isinstance(c.get("pageId"), str) else None,
                    page_type=c.get("pageType") if isinstance(c.get("pageType"), str) else None,
                    entity_type=c.get("entityType")
                    if isinstance(c.get("entityType"), str)
                    else None,
                    canonical_id=c.get("canonicalId")
                    if isinstance(c.get("canonicalId"), str)
                    else None,
                    aliases=c.get("aliases") if isinstance(c.get("aliases"), list) else None,
                    status=c.get("status") if isinstance(c.get("status"), str) else None,
                    confidence=c.get("confidence")
                    if isinstance(c.get("confidence"), int | float)
                    else None,
                    source_ids=c.get("sourceIds") if isinstance(c.get("sourceIds"), list) else None,
                    evidence_kinds=c.get("evidenceKinds")
                    if isinstance(c.get("evidenceKinds"), list)
                    else None,
                    privacy_tiers=c.get("privacyTiers")
                    if isinstance(c.get("privacyTiers"), list)
                    else None,
                    freshness_level=c.get("freshnessLevel")
                    if isinstance(c.get("freshnessLevel"), str)
                    else None,
                    last_touched_at=c.get("lastTouchedAt")
                    if isinstance(c.get("lastTouchedAt"), str)
                    else None,
                )
            )
    return MemoryWikiCompiledCacheSnapshot(digest=digest or {}, claims=claims)


# ── test helpers ──────────────────────────────────────────


def reset_memory_wiki_compiled_cache_for_tests() -> None:
    """Reset module-level state (test-only helper).

    Clears the configured store + the
    in-memory active-vault map so subsequent
    tests start from a clean slate.
    Production code MUST NOT call this.
    """
    global _configured_store, _active_vaults  # noqa: PLW0603 — test-only state
    _configured_store = None
    _active_vaults = {}


__all__ = [
    "ActiveVault",
    "COMPILED_CACHE_MAX_BYTES",
    "COMPILED_CACHE_MAX_BYTES_PER_ENTRY",
    "COMPILED_CACHE_MAX_ENTRIES",
    "COMPILED_CACHE_NAMESPACE",
    "COMPILED_CACHE_VERSION",
    "CompiledCacheBlobStore",
    "CompiledCacheEntry",
    "CompiledCacheMetadata",
    "LEGACY_MEMORY_WIKI_COMPILED_CACHE_PATHS",
    "MemoryWikiCompiledCacheSnapshot",
    "MemoryWikiCompiledCacheStore",
    "MemoryWikiCompiledClaim",
    "MemoryWikiCompiledDigestClaim",
    "MemoryWikiCompiledDigestPage",
    "activate_memory_wiki_compiled_cache_owner",
    "configure_memory_wiki_compiled_cache_store",
    "create_memory_wiki_compiled_cache_publication_id",
    "create_memory_wiki_compiled_cache_store",
    "deactivate_memory_wiki_compiled_cache_owners_except",
    "invalidate_memory_wiki_compiled_cache",
    "load_memory_wiki_compiled_cache",
    "reconcile_memory_wiki_compiled_cache_owner",
    "reset_memory_wiki_compiled_cache_for_tests",
    "resolve_memory_wiki_compiled_cache_generation",
    "resolve_memory_wiki_compiled_cache_owner_id",
    "write_memory_wiki_compiled_cache",
]
