"""Tests for extensions/memory_wiki/log.py.

Phase 4.3a: ports the OpenClaw log helpers
(``appendMemoryWikiLog``,
``loadMemoryWikiVaultIdentity``,
``resolveMemoryWikiVaultSourceGeneration``,
``loadMemoryWikiValidatedVaultIdentity``,
``ensureMemoryWikiVaultGeneration``). The tests
focus on:

- ``append_memory_wiki_log`` writes a single
  JSONL line and creates the parent directory on
  demand.
- ``load_memory_wiki_vault_identity`` returns an
  all-``None`` identity for a missing log.
- ``load_memory_wiki_vault_identity`` walks the
  log linearly, capturing the first non-empty
  ``vaultGeneration`` and the most recent
  publication chain.
- A partial / malformed final line is silently
  skipped.
- ``ensure_memory_wiki_vault_generation`` is
  idempotent: a second call returns the same
  generation as the first.
- ``resolve_memory_wiki_vault_source_generation``
  is deterministic across runs and changes when a
  source file is added.
- ``load_memory_wiki_validated_vault_identity``
  drops a publication when the source tree has
  diverged from the recorded generation.
"""

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
# pyright: reportTypedDictNotRequiredAccess=false

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

from extensions.memory_wiki.log import (  # noqa: E402
    COMPILED_CACHE_PUBLICATION_ID_FIELD,
    COMPILED_CACHE_RESERVATION_ID_FIELD,
    COMPILED_CACHE_SOURCE_GENERATION_FIELD,
    VAULT_GENERATION_FIELD,
    append_memory_wiki_log,
    ensure_memory_wiki_vault_generation,
    load_memory_wiki_validated_vault_identity,
    load_memory_wiki_vault_identity,
    resolve_memory_wiki_vault_source_generation,
)


def _write_log(vault_root: Path, lines: list[dict]) -> Path:
    log_path = vault_root / ".openclaw-wiki" / "log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n",
        encoding="utf-8",
    )
    return log_path


class TestAppendMemoryWikiLog:
    def test_creates_parent_dir_and_writes_line(self, tmp_path: Path) -> None:
        append_memory_wiki_log(
            str(tmp_path),
            {
                "type": "vault-generation",
                "details": {VAULT_GENERATION_FIELD: "gen-1"},
            },
        )
        log_path = tmp_path / ".openclaw-wiki" / "log.jsonl"
        assert log_path.exists()
        line = log_path.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        assert parsed["type"] == "vault-generation"
        assert parsed["details"][VAULT_GENERATION_FIELD] == "gen-1"
        assert "timestamp" in parsed

    def test_appends_multiple_lines(self, tmp_path: Path) -> None:
        append_memory_wiki_log(
            str(tmp_path),
            {"type": "vault-generation", "details": {VAULT_GENERATION_FIELD: "g1"}},
        )
        append_memory_wiki_log(
            str(tmp_path),
            {"type": "init", "details": {}},
        )
        log_path = tmp_path / ".openclaw-wiki" / "log.jsonl"
        text = log_path.read_text(encoding="utf-8")
        assert text.count("\n") == 2


class TestLoadMemoryWikiVaultIdentity:
    def test_missing_log_returns_none_identity(self, tmp_path: Path) -> None:
        identity = load_memory_wiki_vault_identity(str(tmp_path))
        assert identity.vault_generation is None
        assert identity.compiled_cache_publication_id is None
        assert identity.compiled_cache_reservation_id is None
        assert identity.compiled_cache_source_generation is None

    def test_captures_vault_generation(self, tmp_path: Path) -> None:
        _write_log(
            tmp_path,
            [
                {"type": "vault-generation", "details": {VAULT_GENERATION_FIELD: "gen-1"}},
            ],
        )
        identity = load_memory_wiki_vault_identity(str(tmp_path))
        assert identity.vault_generation == "gen-1"

    def test_captures_publication_chain(self, tmp_path: Path) -> None:
        # A commit (line 2) must reference the prior
        # reservation id (res-1) that was already
        # durable in the log; OpenClaw's walker
        # refuses to promote a publication whose
        # reservation diverges from the durable
        # record. ``compiledCacheParentPublicationId``
        # is ``null`` on the first commit (no prior
        # publication yet).
        _write_log(
            tmp_path,
            [
                {
                    "type": "compile",
                    "details": {
                        COMPILED_CACHE_RESERVATION_ID_FIELD: "res-1",
                    },
                },
                {
                    "type": "compile",
                    "details": {
                        COMPILED_CACHE_RESERVATION_ID_FIELD: "res-1",
                        COMPILED_CACHE_PUBLICATION_ID_FIELD: "pub-1",
                        "compiledCacheParentPublicationId": None,
                        COMPILED_CACHE_SOURCE_GENERATION_FIELD: "src-1",
                    },
                },
            ],
        )
        identity = load_memory_wiki_vault_identity(str(tmp_path))
        assert identity.compiled_cache_publication_id == "pub-1"
        assert identity.compiled_cache_source_generation == "src-1"

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        log_path = _write_log(
            tmp_path,
            [
                {"type": "vault-generation", "details": {VAULT_GENERATION_FIELD: "gen-1"}},
            ],
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("{not valid json\n")
        identity = load_memory_wiki_vault_identity(str(tmp_path))
        assert identity.vault_generation == "gen-1"


class TestEnsureMemoryWikiVaultGeneration:
    def test_mints_first_generation(self, tmp_path: Path) -> None:
        gen = ensure_memory_wiki_vault_generation(str(tmp_path))
        assert isinstance(gen, str) and gen
        identity = load_memory_wiki_vault_identity(str(tmp_path))
        assert identity.vault_generation == gen

    def test_idempotent(self, tmp_path: Path) -> None:
        first = ensure_memory_wiki_vault_generation(str(tmp_path))
        second = ensure_memory_wiki_vault_generation(str(tmp_path))
        assert first == second


class TestResolveMemoryWikiVaultSourceGeneration:
    def test_empty_vault_returns_deterministic_hash(self, tmp_path: Path) -> None:
        for sub in ("sources", "entities", "concepts", "syntheses", "reports"):
            (tmp_path / sub).mkdir(parents=True, exist_ok=True)
        h1 = resolve_memory_wiki_vault_source_generation(str(tmp_path))
        h2 = resolve_memory_wiki_vault_source_generation(str(tmp_path))
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_hash_changes_when_source_added(self, tmp_path: Path) -> None:
        for sub in ("sources", "entities", "concepts", "syntheses", "reports"):
            (tmp_path / sub).mkdir(parents=True, exist_ok=True)
        before = resolve_memory_wiki_vault_source_generation(str(tmp_path))
        (tmp_path / "sources" / "alpha.md").write_text("# alpha", encoding="utf-8")
        after = resolve_memory_wiki_vault_source_generation(str(tmp_path))
        assert before != after

    def test_index_md_files_are_excluded(self, tmp_path: Path) -> None:
        (tmp_path / "sources").mkdir(parents=True, exist_ok=True)
        before = resolve_memory_wiki_vault_source_generation(str(tmp_path))
        (tmp_path / "sources" / "index.md").write_text("# index", encoding="utf-8")
        after = resolve_memory_wiki_vault_source_generation(str(tmp_path))
        assert before == after


class TestLoadMemoryWikiValidatedVaultIdentity:
    def test_drops_publication_when_source_diverges(self, tmp_path: Path) -> None:
        # Seed an in-sync source tree.
        for sub in ("sources", "entities", "concepts", "syntheses", "reports"):
            (tmp_path / sub).mkdir(parents=True, exist_ok=True)
        (tmp_path / "sources" / "alpha.md").write_text("# alpha", encoding="utf-8")
        recorded_source_gen = resolve_memory_wiki_vault_source_generation(str(tmp_path))
        _write_log(
            tmp_path,
            [
                {
                    "type": "compile",
                    "details": {
                        COMPILED_CACHE_RESERVATION_ID_FIELD: "res-1",
                    },
                },
                {
                    "type": "compile",
                    "details": {
                        COMPILED_CACHE_RESERVATION_ID_FIELD: "res-1",
                        COMPILED_CACHE_PUBLICATION_ID_FIELD: "pub-1",
                        COMPILED_CACHE_SOURCE_GENERATION_FIELD: recorded_source_gen,
                    },
                },
            ],
        )
        # Pre-mutation identity should trust pub-1.
        pre = load_memory_wiki_validated_vault_identity(str(tmp_path))
        assert pre.compiled_cache_publication_id == "pub-1"
        # Mutate the source tree.
        (tmp_path / "sources" / "beta.md").write_text("# beta", encoding="utf-8")
        post = load_memory_wiki_validated_vault_identity(str(tmp_path))
        # Publication dropped, vault generation preserved.
        assert post.compiled_cache_publication_id is None
        assert post.compiled_cache_source_generation is None
        assert post.vault_generation == pre.vault_generation
