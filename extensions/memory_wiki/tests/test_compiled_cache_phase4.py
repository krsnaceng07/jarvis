"""Tests for extensions/memory_wiki/compiled_cache.py.

Phase 4.3e-mr3: ports the OpenClaw
``compiled-cache.ts`` helpers. The tests
focus on:

- Owner id resolution (global vs agent).
- Publication key derivation (SHA-256).
- Generation hash stability.
- Read / write round-trip via the in-memory
  blob store.
- Active vault activation + reconcile.
- Stale-row rejection (vault generation
  mismatch).
- Owner-scope deactivation.
"""

# ruff: noqa: S108 — the "/tmp/..." paths are test fixtures mirroring the OpenClaw TS source

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

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.memory_wiki.compiled_cache import (  # noqa: E402
    COMPILED_CACHE_MAX_ENTRIES,
    COMPILED_CACHE_NAMESPACE,
    COMPILED_CACHE_VERSION,
    LEGACY_MEMORY_WIKI_COMPILED_CACHE_PATHS,
    MemoryWikiCompiledCacheSnapshot,
    MemoryWikiCompiledClaim,
    activate_memory_wiki_compiled_cache_owner,
    configure_memory_wiki_compiled_cache_store,
    create_memory_wiki_compiled_cache_publication_id,
    create_memory_wiki_compiled_cache_store,
    deactivate_memory_wiki_compiled_cache_owners_except,
    invalidate_memory_wiki_compiled_cache,
    load_memory_wiki_compiled_cache,
    reconcile_memory_wiki_compiled_cache_owner,
    reset_memory_wiki_compiled_cache_for_tests,
    resolve_memory_wiki_compiled_cache_generation,
    resolve_memory_wiki_compiled_cache_owner_id,
    write_memory_wiki_compiled_cache,
)


def _config(
    *, scope: str = "global", agent_id: str | None = None, vault_path: str | None = None
) -> SimpleNamespace:
    # Use the test runner's actual tmp dir
    # so the absolute path is consistent
    # across Windows / POSIX.
    if vault_path is None:
        import tempfile

        vault_path = tempfile.mkdtemp(prefix="memory-wiki-cache-test-")
    return SimpleNamespace(
        vault=SimpleNamespace(scope=scope, path=vault_path),
        agent_id=agent_id,
    )


def _snapshot(
    *,
    claim_text: str = "hello",
    claim_status: str = "supported",
) -> MemoryWikiCompiledCacheSnapshot:
    return MemoryWikiCompiledCacheSnapshot(
        digest={
            "claimCount": 1,
            "contradictionCount": 0,
            "pages": [],
        },
        claims=[
            MemoryWikiCompiledClaim(
                page_title="X",
                page_kind="entity",
                page_path="entities/x.md",
                text=claim_text,
                status=claim_status,
            )
        ],
    )


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset module-level state before and after each test."""
    reset_memory_wiki_compiled_cache_for_tests()
    yield
    reset_memory_wiki_compiled_cache_for_tests()


class TestConstants:
    def test_namespace(self) -> None:
        assert COMPILED_CACHE_NAMESPACE == "compiled-cache"
        assert COMPILED_CACHE_VERSION == 2
        assert COMPILED_CACHE_MAX_ENTRIES == 256

    def test_legacy_paths(self) -> None:
        assert ".openclaw-wiki/cache/agent-digest.json" in (LEGACY_MEMORY_WIKI_COMPILED_CACHE_PATHS)
        assert ".openclaw-wiki/cache/claims.jsonl" in (LEGACY_MEMORY_WIKI_COMPILED_CACHE_PATHS)


class TestOwnerResolution:
    def test_global_owner(self) -> None:
        assert resolve_memory_wiki_compiled_cache_owner_id(_config(scope="global")) == "global"

    def test_agent_owner(self) -> None:
        assert (
            resolve_memory_wiki_compiled_cache_owner_id(_config(scope="agent", agent_id="alpha"))
            == "agent:alpha"
        )

    def test_agent_scope_without_id_raises(self) -> None:
        with pytest.raises(ValueError, match="agent owner"):
            resolve_memory_wiki_compiled_cache_owner_id(_config(scope="agent", agent_id=None))


class TestPublicationId:
    def test_publication_id_is_uuid(self) -> None:
        pid = create_memory_wiki_compiled_cache_publication_id()
        # A UUID has the form
        # ``8-4-4-4-12`` hex chars.
        assert len(pid) == 36
        assert pid.count("-") == 4


class TestGeneration:
    def test_generation_is_stable(self) -> None:
        snap = _snapshot(claim_text="same")
        gen1 = resolve_memory_wiki_compiled_cache_generation(snap)
        gen2 = resolve_memory_wiki_compiled_cache_generation(snap)
        assert gen1 == gen2
        assert len(gen1) == 64  # SHA-256 hex

    def test_generation_changes_with_payload(self) -> None:
        snap_a = _snapshot(claim_text="alpha")
        snap_b = _snapshot(claim_text="beta")
        gen_a = resolve_memory_wiki_compiled_cache_generation(snap_a)
        gen_b = resolve_memory_wiki_compiled_cache_generation(snap_b)
        assert gen_a != gen_b


class TestActivation:
    def test_activate_with_empty_generation_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            activate_memory_wiki_compiled_cache_owner(_config(), vault_generation="   ")

    def test_activate_then_deactivate(self) -> None:
        activate_memory_wiki_compiled_cache_owner(_config(), vault_generation="gen-1")
        # Two owners, then deactivate except A.
        activate_memory_wiki_compiled_cache_owner(_config(agent_id="b"), vault_generation="gen-2")
        deactivate_memory_wiki_compiled_cache_owners_except({"global"})
        # Loading with the global config still
        # works (the active vault is registered).
        # The agent config no longer has an
        # active vault.
        from extensions.memory_wiki.compiled_cache import (
            _resolve_active_vault,
        )

        assert _resolve_active_vault(_config(scope="agent", agent_id="b")) is None


class TestStoreRoundTrip:
    def test_write_then_read(self) -> None:
        config = _config()
        store = create_memory_wiki_compiled_cache_store()
        activate_memory_wiki_compiled_cache_owner(config, "gen-1")
        # Mark reconciled by hand.
        from extensions.memory_wiki.compiled_cache import _active_vaults

        _active_vaults["global"] = _active_vaults["global"].__class__(
            path=_active_vaults["global"].path,
            vault_generation=_active_vaults["global"].vault_generation,
            compiled_cache_publication_id="pub-1",
            reconciled=True,
        )
        snap = _snapshot()
        generation = resolve_memory_wiki_compiled_cache_generation(snap)
        store.write(config, snap, generation, "pub-1")
        # Re-activate with the publication id
        # so ``read`` returns the snapshot.
        activate_memory_wiki_compiled_cache_owner(
            config, "gen-1", compiled_cache_publication_id="pub-1"
        )
        # Manually mark reconciled.
        from extensions.memory_wiki.compiled_cache import _active_vaults

        _active_vaults["global"] = _active_vaults["global"].__class__(
            path=_active_vaults["global"].path,
            vault_generation=_active_vaults["global"].vault_generation,
            compiled_cache_publication_id="pub-1",
            reconciled=True,
        )
        read_back = store.read(config)
        assert read_back is not None
        assert read_back.claims[0].text == "hello"

    def test_read_without_reconcile_returns_none(self) -> None:
        config = _config()
        store = create_memory_wiki_compiled_cache_store()
        activate_memory_wiki_compiled_cache_owner(
            config, "gen-1", compiled_cache_publication_id="pub-1"
        )
        # reconciled=False → returns None
        # (because the vault isn't confirmed).
        assert store.read(config) is None

    def test_write_without_active_vault_raises(self) -> None:
        store = create_memory_wiki_compiled_cache_store()
        with pytest.raises(ValueError, match="not active"):
            store.write(_config(), _snapshot(), "g", "p")

    def test_write_with_mismatched_generation_raises(self) -> None:
        config = _config()
        store = create_memory_wiki_compiled_cache_store()
        activate_memory_wiki_compiled_cache_owner(config, "gen-1")
        with pytest.raises(ValueError, match="does not match"):
            store.write(config, _snapshot(), "wrong-gen", "pub-1")


class TestPublicHelpers:
    def test_load_without_configured_store_raises(self) -> None:
        with pytest.raises(ValueError, match="not configured"):
            load_memory_wiki_compiled_cache(_config())

    def test_invalidate_without_configured_store_raises(self) -> None:
        with pytest.raises(ValueError, match="not configured"):
            invalidate_memory_wiki_compiled_cache(_config())

    def test_configure_then_load(self) -> None:
        store = create_memory_wiki_compiled_cache_store()
        configure_memory_wiki_compiled_cache_store(store)
        # No active vault → load returns None.
        assert load_memory_wiki_compiled_cache(_config()) is None
        # configure(None) clears the store.
        configure_memory_wiki_compiled_cache_store(None)


class TestReconcile:
    def test_reconcile_marks_active(self) -> None:
        config = _config()
        store = create_memory_wiki_compiled_cache_store()
        configure_memory_wiki_compiled_cache_store(store)
        activate_memory_wiki_compiled_cache_owner(config, "gen-1")

        identity: dict[str, str | None] = {
            "vaultGeneration": "gen-1",
            "compiledCachePublicationId": None,
        }
        reconcile_memory_wiki_compiled_cache_owner(config, lambda: identity)
        # The active vault is now ``reconciled``.
        from extensions.memory_wiki.compiled_cache import (
            _active_vaults,
        )

        assert _active_vaults["global"].reconciled is True

    def test_reconcile_drops_on_identity_mismatch(self) -> None:
        config = _config()
        store = create_memory_wiki_compiled_cache_store()
        configure_memory_wiki_compiled_cache_store(store)
        activate_memory_wiki_compiled_cache_owner(config, "gen-1")

        # First call returns gen-1; the second
        # call (the "confirmed" identity)
        # returns gen-2 → mismatch.
        identity_a: dict[str, str | None] = {
            "vaultGeneration": "gen-1",
            "compiledCachePublicationId": None,
        }
        identity_b: dict[str, str | None] = {
            "vaultGeneration": "gen-2",
            "compiledCachePublicationId": None,
        }
        iter_identity = iter([identity_a, identity_b])
        reconcile_memory_wiki_compiled_cache_owner(config, lambda: next(iter_identity))
        # The active vault was dropped
        # (mismatch).
        from extensions.memory_wiki.compiled_cache import (
            _resolve_active_vault,
        )

        assert _resolve_active_vault(config) is None


class TestPublicWrite:
    def test_write_memory_wiki_compiled_cache_round_trip(self) -> None:
        config = _config()
        store = create_memory_wiki_compiled_cache_store()
        configure_memory_wiki_compiled_cache_store(store)
        activate_memory_wiki_compiled_cache_owner(config, "gen-1")
        snap = _snapshot()
        generation = resolve_memory_wiki_compiled_cache_generation(snap)
        publication_id = create_memory_wiki_compiled_cache_publication_id()
        write_memory_wiki_compiled_cache(
            config,
            snap,
            generation,
            publication_id,
            None,
            lambda: None,  # validate
            lambda: None,  # commit
            lambda: {
                "vaultGeneration": "gen-1",
                "compiledCachePublicationId": publication_id,
            },
        )
        # The active vault now has the
        # publication id + is reconciled.
        from extensions.memory_wiki.compiled_cache import (
            _active_vaults,
        )

        active = _active_vaults["global"]
        assert active.reconciled is True
        assert active.compiled_cache_publication_id == publication_id

    def test_write_rejects_validation_failure(self) -> None:
        config = _config()
        store = create_memory_wiki_compiled_cache_store()
        configure_memory_wiki_compiled_cache_store(store)
        activate_memory_wiki_compiled_cache_owner(config, "gen-1")
        snap = _snapshot()
        generation = resolve_memory_wiki_compiled_cache_generation(snap)
        publication_id = create_memory_wiki_compiled_cache_publication_id()

        def _validate() -> None:
            raise RuntimeError("validation failed")

        with pytest.raises(RuntimeError, match="validation failed"):
            write_memory_wiki_compiled_cache(
                config,
                snap,
                generation,
                publication_id,
                None,
                _validate,
                lambda: None,
                lambda: {
                    "vaultGeneration": "gen-1",
                    "compiledCachePublicationId": publication_id,
                },
            )
        # The publication was deleted.
        from extensions.memory_wiki.compiled_cache import (
            _publication_key,
        )

        assert store.blob_store.lookup(_publication_key("global", publication_id)) is None
