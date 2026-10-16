"""log — vault audit log + identity resolution.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/log.ts``.

The memory-wiki vault keeps a single
``.openclaw-wiki/log.jsonl`` audit log. Every
significant event (``init``, ``vault-generation``,
``ingest``, ``okf-import``, ``compile``, ``lint``)
appends one JSON object. The log is the durable
identity anchor: a freshly-initialized vault has no
``vaultGeneration``; the first ``vault-generation``
entry mints a UUID, and concurrent initializers
converge on whichever entry is durable first.

The Python port preserves the linear-walk loader
contract: malformed JSON lines (typically a partial
final line after an interrupted append) are silently
skipped. The causal publication chain
(``compiledCacheReservationId`` →
``compiledCachePublicationId`` →
``compiledCacheSourceGeneration``) is enforced during
the walk so a tampered / truncated log can't promote
a publication without a matching source-tree hash.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import time
from typing import Any

from jarvis_sdk import append_regular_file

from .time import resolve_memory_wiki_timestamp
from .types import MemoryWikiLogEntryType, MemoryWikiVaultIdentity

# Module-level constants mirror OpenClaw's:
#   const VAULT_GENERATION_FIELD = "vaultGeneration";
#   const COMPILED_CACHE_RESERVATION_ID_FIELD = "compiledCacheReservationId";
#   const COMPILED_CACHE_PUBLICATION_ID_FIELD = "compiledCachePublicationId";
#   const COMPILED_CACHE_PARENT_PUBLICATION_ID_FIELD = "compiledCacheParentPublicationId";
#   const COMPILED_CACHE_SOURCE_GENERATION_FIELD = "compiledCacheSourceGeneration";
#   const COMPILED_SOURCE_DIRECTORIES = ["sources", "entities", "concepts", "syntheses", "reports"];
VAULT_GENERATION_FIELD = "vaultGeneration"
COMPILED_CACHE_RESERVATION_ID_FIELD = "compiledCacheReservationId"
COMPILED_CACHE_PUBLICATION_ID_FIELD = "compiledCachePublicationId"
COMPILED_CACHE_PARENT_PUBLICATION_ID_FIELD = "compiledCacheParentPublicationId"
COMPILED_CACHE_SOURCE_GENERATION_FIELD = "compiledCacheSourceGeneration"

COMPILED_SOURCE_DIRECTORIES = (
    "sources",
    "entities",
    "concepts",
    "syntheses",
    "reports",
)

# The vault log file lives under the .openclaw-wiki
# directory; the directory itself is initialized by
# ``vault.py`` in Phase 4.3c.
LOG_RELATIVE_PATH = os.path.join(".openclaw-wiki", "log.jsonl")


def _vault_log_path(vault_root: str) -> str:
    """Return the absolute path of the vault audit log.

    Mirrors the inline ``path.join(vaultRoot, ".openclaw-wiki", "log.jsonl")``
    in OpenClaw's ``appendMemoryWikiLog``.
    """
    return os.path.join(vault_root, ".openclaw-wiki", "log.jsonl")


def append_memory_wiki_log(
    vault_root: str,
    entry: dict[str, Any],
) -> None:
    """Append one JSONL entry to the vault audit log.

    Mirrors OpenClaw's ``appendMemoryWikiLog``. The
    entry's ``timestamp`` is auto-filled when missing,
    and the parent directory is created on demand.
    Rejects symlink parents (matches the OpenClaw
    ``rejectSymlinkParents: true`` flag on
    ``appendRegularFile``).
    """
    log_path = _vault_log_path(vault_root)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    if "timestamp" not in entry:
        entry = {**entry, "timestamp": resolve_memory_wiki_timestamp()}
    append_regular_file(
        log_path,
        json.dumps(entry, ensure_ascii=False) + "\n",
        reject_symlink_parents=True,
    )


def load_memory_wiki_vault_identity(
    vault_root: str,
) -> MemoryWikiVaultIdentity:
    """Read the durable vault identity from the log.

    Mirrors OpenClaw's ``loadMemoryWikiVaultIdentity``.
    Returns a fresh ``MemoryWikiVaultIdentity`` with
    all four fields ``None`` when the log file is
    absent. A partial / malformed final line is
    silently skipped. The causal publication chain
    is enforced: a commit is only accepted if the
    prior publication id and reservation id both
    match what is already durable in the log, and
    the ``compiledCacheSourceGeneration`` is present.
    """
    log_path = _vault_log_path(vault_root)
    try:
        with open(log_path, encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return MemoryWikiVaultIdentity()
    except OSError:
        # Permission errors, transient FS issues,
        # etc. are treated the same as "no log yet".
        return MemoryWikiVaultIdentity()

    vault_generation: str | None = None
    compiled_cache_reservation_id: str | None = None
    compiled_cache_publication_id: str | None = None
    compiled_cache_source_generation: str | None = None

    for line in raw.splitlines():
        try:
            parsed: Any = json.loads(line)
        except ValueError:
            # Audit logs may contain a partial final
            # line after an interrupted append.
            continue
        if not isinstance(parsed, dict):
            continue
        details = parsed.get("details")
        details_dict = details if isinstance(details, dict) else {}

        candidate_vault_generation = details_dict.get(VAULT_GENERATION_FIELD)
        if (
            vault_generation is None
            and isinstance(candidate_vault_generation, str)
            and candidate_vault_generation.strip()
        ):
            vault_generation = candidate_vault_generation.strip()

        candidate_reservation_id = details_dict.get(COMPILED_CACHE_RESERVATION_ID_FIELD)
        normalized_reservation_id: str | None = None
        if isinstance(candidate_reservation_id, str) and candidate_reservation_id.strip():
            normalized_reservation_id = candidate_reservation_id.strip()

        candidate_publication_id = details_dict.get(COMPILED_CACHE_PUBLICATION_ID_FIELD)
        if isinstance(candidate_publication_id, str) and candidate_publication_id.strip():
            candidate_parent = details_dict.get(COMPILED_CACHE_PARENT_PUBLICATION_ID_FIELD)
            normalized_parent: str | None | object = None
            if candidate_parent is None:
                normalized_parent = None
            elif isinstance(candidate_parent, str) and candidate_parent.strip():
                normalized_parent = candidate_parent.strip()
            else:
                normalized_parent = None

            candidate_source_generation = details_dict.get(COMPILED_CACHE_SOURCE_GENERATION_FIELD)
            normalized_source_generation: str | None = None
            if isinstance(candidate_source_generation, str) and candidate_source_generation.strip():
                normalized_source_generation = candidate_source_generation.strip()

            # A commit must reference both the prior
            # publication and a reservation already
            # present in the log; it cannot recreate
            # either after rollback.
            if (
                normalized_parent == compiled_cache_publication_id
                and normalized_reservation_id == compiled_cache_reservation_id
                and normalized_source_generation
            ):
                compiled_cache_publication_id = candidate_publication_id.strip()
                compiled_cache_source_generation = normalized_source_generation
        elif normalized_reservation_id:
            compiled_cache_reservation_id = normalized_reservation_id

    return MemoryWikiVaultIdentity(
        vault_generation=vault_generation,
        compiled_cache_reservation_id=compiled_cache_reservation_id,
        compiled_cache_publication_id=compiled_cache_publication_id,
        compiled_cache_source_generation=compiled_cache_source_generation,
    )


def resolve_memory_wiki_vault_source_generation(vault_root: str) -> str:
    """Compute a deterministic SHA-256 over the source tree.

    Mirrors OpenClaw's
    ``resolveMemoryWikiVaultSourceGeneration``. The
    hash covers the relative path + content of every
    ``.md`` file under
    ``{sources,entities,concepts,syntheses,reports}/``,
    excluding the auto-generated ``index.md`` files
    in each directory. The relative path is
    lowercased on Windows to match the case-insensitive
    artifact-key resolver in ``source_path_shared.py``.
    """
    files: list[tuple[str, str]] = []
    for relative_dir in COMPILED_SOURCE_DIRECTORIES:
        dir_path = os.path.join(vault_root, relative_dir)
        if not os.path.isdir(dir_path):
            continue
        for current_root, _dirs, names in os.walk(dir_path):
            for name in names:
                if not name.endswith(".md"):
                    continue
                absolute_path = os.path.join(current_root, name)
                relative_path = os.path.relpath(absolute_path, vault_root)
                # Use forward slashes in the hash to
                # match OpenClaw's ``path.sep.join("/")``
                # normalization (Windows-friendly).
                relative_path = relative_path.replace(os.sep, "/")
                if os.path.basename(relative_path) == "index.md":
                    continue
                files.append((relative_path, absolute_path))

    files.sort(key=lambda pair: pair[0])
    digest = hashlib.sha256()
    for relative_path, absolute_path in files:
        normalized_path = relative_path.lower() if sys.platform == "win32" else relative_path
        path_bytes = normalized_path.encode("utf-8")
        path_length = len(path_bytes).to_bytes(4, byteorder="big", signed=False)
        try:
            with open(absolute_path, "rb") as f:
                content_digest = hashlib.sha256(f.read()).digest()
        except OSError:
            # A transient read error on a single file
            # would diverge the source tree from the
            # recorded generation. Treat it as empty
            # bytes for the per-file digest so the
            # overall hash still converges.
            content_digest = hashlib.sha256(b"").digest()
        digest.update(path_length)
        digest.update(path_bytes)
        digest.update(content_digest)
    return digest.hexdigest()


def load_memory_wiki_validated_vault_identity(
    vault_root: str,
) -> MemoryWikiVaultIdentity:
    """Like ``load_memory_wiki_vault_identity`` but re-hashes the source tree.

    Mirrors OpenClaw's ``loadMemoryWikiValidatedVaultIdentity``.
    If a published ``compiledCachePublicationId`` is
    recorded but the current source-tree hash
    diverges from the recorded
    ``compiledCacheSourceGeneration``, the publication
    fields are dropped (the publication is no longer
    trustworthy). The vault generation is preserved.
    """
    identity = load_memory_wiki_vault_identity(vault_root)
    if not identity.compiled_cache_publication_id or not identity.compiled_cache_source_generation:
        return identity
    if (
        resolve_memory_wiki_vault_source_generation(vault_root)
        == identity.compiled_cache_source_generation
    ):
        return identity
    return MemoryWikiVaultIdentity(
        vault_generation=identity.vault_generation,
        compiled_cache_reservation_id=identity.compiled_cache_reservation_id,
        compiled_cache_publication_id=None,
        compiled_cache_source_generation=None,
    )


def _load_memory_wiki_vault_generation(
    vault_root: str,
) -> str | None:
    """Internal helper — the vault-generation field of the identity.

    Mirrors OpenClaw's local
    ``loadMemoryWikiVaultGeneration`` function used
    inside ``ensureMemoryWikiVaultGeneration``.
    """
    return load_memory_wiki_vault_identity(vault_root).vault_generation


def ensure_memory_wiki_vault_generation(vault_root: str) -> str:
    """Return a stable ``vaultGeneration`` for ``vault_root``.

    Mirrors OpenClaw's ``ensureMemoryWikiVaultGeneration``.
    If the log already records one, returns the
    durable value. Otherwise mints a fresh UUID,
    appends a ``vault-generation`` entry, and
    converges on whichever entry is durable first
    (concurrent initializers may append two
    candidates; the first one wins).
    """
    existing = _load_memory_wiki_vault_generation(vault_root)
    if existing:
        return existing
    candidate = secrets.token_hex(16)  # 32-char hex string, like UUID without dashes
    # OpenClaw uses ``randomUUID()`` which is a 36-char
    # UUID; Python's ``uuid4`` would also work but
    # ``secrets.token_hex(16)`` matches the
    # "lowercase hex, 32 chars" shape without the
    # extra dependency.
    append_memory_wiki_log(
        vault_root,
        {
            "type": "vault-generation",
            "timestamp": resolve_memory_wiki_timestamp(int(time.time() * 1000)),
            "details": {VAULT_GENERATION_FIELD: candidate},
        },
    )
    # Concurrent initialization can append two
    # candidates. The first durable audit entry
    # owns the vault generation, so every caller
    # converges on it.
    durable = _load_memory_wiki_vault_generation(vault_root)
    return durable if durable else candidate


# Phase 4.3a is sync-only; the rest of the audit
# pipeline (``type`` discriminated union, etc.) is
# built on top of these primitives in Phase 4.3c+.
__all__ = [
    "COMPILED_CACHE_PARENT_PUBLICATION_ID_FIELD",
    "COMPILED_CACHE_PUBLICATION_ID_FIELD",
    "COMPILED_CACHE_RESERVATION_ID_FIELD",
    "COMPILED_CACHE_SOURCE_GENERATION_FIELD",
    "COMPILED_SOURCE_DIRECTORIES",
    "LOG_RELATIVE_PATH",
    "VAULT_GENERATION_FIELD",
    "append_memory_wiki_log",
    "ensure_memory_wiki_vault_generation",
    "load_memory_wiki_validated_vault_identity",
    "load_memory_wiki_vault_identity",
    "resolve_memory_wiki_vault_source_generation",
]


# Type re-export so callers can validate entry shape
# without importing from ``types.py`` directly.
MemoryWikiLogEntry = dict[str, Any]


def _validate_entry_type(entry_type: str) -> MemoryWikiLogEntryType:
    """Internal: narrow ``entry_type`` to the known union.

    Used by future sub-phases that need a typed log
    write. Phase 4.3a only emits ``vault-generation``,
    so this is a forward-looking helper.
    """
    if entry_type not in {
        "init",
        "vault-generation",
        "ingest",
        "okf-import",
        "compile",
        "lint",
    }:
        raise ValueError(f"unknown memory-wiki log entry type: {entry_type!r}")
    return entry_type  # type: ignore[return-value]
