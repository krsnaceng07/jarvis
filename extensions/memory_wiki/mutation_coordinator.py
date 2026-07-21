"""mutation_coordinator — vault-key resolution + per-vault async lock.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/mutation-coordinator.ts``.

The memory-wiki compile / apply / obsidian subcommands
all perform read-modify-write transactions on the
vault directory. To keep the on-disk state
consistent under concurrent callers, the plugin
serializes all mutations on a per-vault basis via
a per-key async queue plus a small AsyncLocalStorage-
style "active mutation" flag that lets nested
``withMemoryWikiVaultMutation`` calls re-enter
without deadlocking.

The Python port preserves the same shape:
- ``resolveMemoryWikiVaultMutationKey(vaultPath)`` --
  canonicalize the vault path (Windows lowercased;
  POSIX as-is) and resolve any symlinks via
  ``os.path.realpath``. Cache the resolved key
  in a process-level dict (bounded at 256 entries
  to match OpenClaw's ``MAX_CACHED_VAULT_KEYS``).
- ``withMemoryWikiVaultMutation(vaultPath, fn)`` --
  acquire the per-vault lease; run ``fn``; release
  the lease. Nested calls re-enter via the
  AsyncLocalStorage flag instead of double-locking.

Dependencies: stdlib only.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import os
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportReturnType=false


MAX_CACHED_VAULT_KEYS = 256


def _normalize_canonical_vault_key(vault_path: str) -> str:
    """Return the canonical form of ``vault_path``.

    Mirrors OpenClaw's ``normalizeCanonicalVaultKey``.
    On Windows the filesystem is case-insensitive so
    the path is lowercased; on POSIX the case is
    preserved.
    """
    if sys.platform == "win32":
        return vault_path.lower()
    return vault_path


async def _resolve_canonical_vault_key(resolved_path: str) -> str:
    """Resolve a vault path to its realpath, with ancestor-walk fallback.

    Mirrors OpenClaw's ``resolveCanonicalVaultKey``. If
    ``os.path.realpath`` raises ``OSError``
    (``ENOENT`` / ``ENOTDIR`` -- the path doesn't
    exist yet), the function walks up the parent
    chain, accumulates the missing suffix, and
    resolves an existing ancestor.
    """
    suffix: list[str] = []
    candidate = resolved_path
    while True:
        try:
            existing_path = os.path.realpath(candidate)
        except OSError as exc:
            code = getattr(exc, "errno", None)
            if code not in (os.errno.ENOENT, os.errno.ENOTDIR):
                # Other errors (EACCES, ELOOP, ...) are
                # fatal; fall back to the lexical path.
                return _normalize_canonical_vault_key(resolved_path)
            parent = os.path.dirname(candidate)
            if parent == candidate:
                # Reached the filesystem root without
                # finding an existing ancestor.
                return _normalize_canonical_vault_key(resolved_path)
            suffix.insert(0, os.path.basename(candidate))
            candidate = parent
            continue
        # ``os.path.realpath`` does not auto-append
        # ``os.sep``, so re-join manually.
        joined = os.path.join(existing_path, *suffix) if suffix else existing_path
        return _normalize_canonical_vault_key(joined)


# Module-level cache: ``{resolved_input_path: asyncio.Future[str>}``.
# Mirrors OpenClaw's ``canonicalVaultKeys`` map; the
# Python port uses a ``dict`` of pending
# ``asyncio.Future`` so concurrent
# ``resolveMemoryWikiVaultMutationKey`` calls share
# the same realpath resolution.
_canonical_vault_keys: dict[str, asyncio.Future[str]] = {}


async def resolve_memory_wiki_vault_mutation_key(vault_path: str) -> str:
    """Return the canonical mutation key for ``vault_path``.

    Mirrors OpenClaw's
    ``resolveMemoryWikiVaultMutationKey``. The
    resolved key is cached process-wide; the cache
    is bounded at ``MAX_CACHED_VAULT_KEYS`` so
    request-time mutations never freshness-poll
    paths.
    """
    resolved_input = os.path.abspath(vault_path)
    cached = _canonical_vault_keys.get(resolved_input)
    if cached is not None:
        return await asyncio.shield(cached)

    if len(_canonical_vault_keys) >= MAX_CACHED_VAULT_KEYS:
        # Evict the oldest insertion. ``next(iter)``
        # returns the first-inserted key.
        oldest = next(iter(_canonical_vault_keys))
        _canonical_vault_keys.pop(oldest, None)

    future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
    future.set_result(await _resolve_canonical_vault_key(resolved_input))
    _canonical_vault_keys[resolved_input] = future
    return future.result()


# AsyncLocalStorage-equivalent: ``contextvars`` carries
# the active-mutation set across awaits without
# leaking across concurrent tasks.
_active_vault_mutations: contextvars.ContextVar[dict[str, dict[str, bool]] | None] = (
    contextvars.ContextVar("active_vault_mutations", default=None)
)


# Per-vault async lock. A plain ``dict`` of
# ``asyncio.Lock`` instances preserves the
# OpenClaw ``KeyedAsyncQueue`` semantics (one
# concurrent mutation per vault; different vaults
# run in parallel).
_vault_locks: dict[str, asyncio.Lock] = {}


def _get_vault_lock(key: str) -> asyncio.Lock:
    """Return the per-vault async lock, creating it on first use."""
    lock = _vault_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _vault_locks[key] = lock
    return lock


@contextlib.asynccontextmanager
async def _vault_mutation_scope(key: str, lease: dict[str, bool]) -> Any:
    """Async context manager that pushes / pops the active-mutation map.

    Mirrors OpenClaw's
    ``activeVaultMutations.run(nextActive, mutation)``
    AsyncLocalStorage round-trip. The Python
    equivalent uses ``contextvars`` so the
    flag survives the await boundary without
    leaking across concurrent tasks.
    """
    active = _active_vault_mutations.get()
    next_active: dict[str, dict[str, bool]] = dict(active) if active else {}
    next_active[key] = lease
    token = _active_vault_mutations.set(next_active)
    try:
        yield
    finally:
        _active_vault_mutations.reset(token)


async def with_memory_wiki_vault_mutation(
    vault_path: str,
    mutation: Callable[[], Awaitable[Any]],
) -> Any:
    """Run ``mutation`` under the per-vault mutation lock.

    Mirrors OpenClaw's ``withMemoryWikiVaultMutation``.
    Nested calls re-enter (no double-locking); the
    lease is marked inactive when the outer call
    exits so later work queues instead of bypassing
    serialization.
    """
    key = await resolve_memory_wiki_vault_mutation_key(vault_path)
    active = _active_vault_mutations.get()
    if active is not None and active.get(key, {}).get("active", False):
        return await mutation()

    lease: dict[str, bool] = {"active": True}
    lock = _get_vault_lock(key)
    async with lock, _vault_mutation_scope(key, lease):
        try:
            return await mutation()
        finally:
            # Detached children inherit this object.
            # Mark it inactive when the owner exits
            # so later work queues instead of
            # bypassing serialization.
            lease["active"] = False


async def reset_memory_wiki_mutation_state_for_tests() -> None:
    """Reset module-level state. Test-only helper.

    Clears the canonical-key cache and the per-vault
    lock map so subsequent tests start from a clean
    slate. Production code MUST NOT call this.
    """
    _canonical_vault_keys.clear()
    _vault_locks.clear()


__all__ = [
    "MAX_CACHED_VAULT_KEYS",
    "reset_memory_wiki_mutation_state_for_tests",
    "resolve_memory_wiki_vault_mutation_key",
    "with_memory_wiki_vault_mutation",
]
