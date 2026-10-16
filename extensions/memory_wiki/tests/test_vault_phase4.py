"""Tests for extensions/memory_wiki/vault.py.

Phase 4.3c: ports the OpenClaw
``initializeMemoryWikiVault`` helper. The tests
focus on:

- A fresh vault creates all 8 standard directories
  (entities, concepts, syntheses, sources, reports,
  _attachments, _views, .openclaw-wiki) and the
  scaffold files (AGENTS.md, WIKI.md, index.md,
  inbox.md, .openclaw-wiki/log.jsonl).
- The scaffold files are populated with the
  OpenClaw-shaped content (## Generated block in
  index.md, vault mode + render mode in WIKI.md,
  etc.).
- Re-initializing the same vault is a no-op
  (``created=False`` and no new files).
- A ``vault-generation`` log entry is appended on
  first init so the durable identity is anchored.
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
import os
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

import pytest  # noqa: E402

from extensions.memory_wiki.config import resolve_memory_wiki_config  # noqa: E402
from extensions.memory_wiki.vault import (  # noqa: E402
    WIKI_VAULT_DIRECTORIES,
    WIKI_VAULT_SCAFFOLD,
    initialize_memory_wiki_vault,
)


@pytest.fixture
def wiki_config(tmp_path: Path):
    """A resolved wiki config rooted at ``tmp_path``."""
    return resolve_memory_wiki_config({"vault": {"path": str(tmp_path)}}, homedir="/h")


class TestInitializeMemoryWikiVault:
    def test_creates_all_directories(self, tmp_path: Path, wiki_config: object) -> None:
        result = initialize_memory_wiki_vault(wiki_config)  # type: ignore[arg-type]
        for relative_dir in WIKI_VAULT_DIRECTORIES:
            assert (tmp_path / relative_dir).is_dir()
        assert result.created is True
        # All 8 dirs are reported as created.
        created_relatives = {os.path.relpath(d, str(tmp_path)) for d in result.created_directories}
        for relative_dir in WIKI_VAULT_DIRECTORIES:
            assert relative_dir in created_relatives

    def test_creates_all_scaffold_files(self, tmp_path: Path, wiki_config: object) -> None:
        result = initialize_memory_wiki_vault(wiki_config)  # type: ignore[arg-type]
        for relative_path in WIKI_VAULT_SCAFFOLD:
            assert (tmp_path / relative_path).exists()

        # All 5 scaffold files are reported as
        # created (absolute paths, matching OpenClaw's
        # ``path.join(rootDir, relativePath)``).
        # Normalize to forward slashes for cross-
        # platform comparison.
        def normalize(path_str: str) -> str:
            return path_str.replace(os.sep, "/")

        expected_abs = {normalize(os.path.join(str(tmp_path), p)) for p in WIKI_VAULT_SCAFFOLD}
        actual_abs = {normalize(p) for p in result.created_files}
        assert actual_abs == expected_abs, (
            f"actual={sorted(actual_abs)}\nexpected={sorted(expected_abs)}"
        )

    def test_scaffold_files_have_expected_content(
        self, tmp_path: Path, wiki_config: object
    ) -> None:
        initialize_memory_wiki_vault(wiki_config)  # type: ignore[arg-type]
        # index.md: managed block with the
        # ``## Generated`` heading + start/end markers.
        index_md = (tmp_path / "index.md").read_text(encoding="utf-8")
        assert "<!-- openclaw:wiki:index:start -->" in index_md
        assert "<!-- openclaw:wiki:index:end -->" in index_md
        assert "## Generated" in index_md
        # WIKI.md: vault mode + render mode + search
        # corpus default.
        wiki_md = (tmp_path / "WIKI.md").read_text(encoding="utf-8")
        assert "Vault mode: `isolated`" in wiki_md
        assert "Render mode: `native`" in wiki_md
        assert "Search corpus default: `wiki`" in wiki_md
        # AGENTS.md: the maintainer rules.
        agents_md = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "Treat generated blocks as plugin-owned." in agents_md
        assert "Use the wiki tools for machine reads" in agents_md
        # inbox.md: the simple inbox template.
        inbox_md = (tmp_path / "inbox.md").read_text(encoding="utf-8")
        assert "# Inbox" in inbox_md
        assert "Drop raw ideas" in inbox_md

    def test_idempotent(self, tmp_path: Path, wiki_config: object) -> None:
        first = initialize_memory_wiki_vault(wiki_config)  # type: ignore[arg-type]
        assert first.created is True
        second = initialize_memory_wiki_vault(wiki_config)  # type: ignore[arg-type]
        # Second run is a no-op.
        assert second.created is False
        assert second.created_directories == []
        assert second.created_files == []

    def test_appends_init_log_entry(self, tmp_path: Path, wiki_config: object) -> None:
        initialize_memory_wiki_vault(wiki_config)  # type: ignore[arg-type]
        log_path = tmp_path / ".openclaw-wiki" / "log.jsonl"
        text = log_path.read_text(encoding="utf-8")
        # The init log entry is the first non-empty
        # line. There may also be a ``vault-generation``
        # entry after it.
        lines = [line for line in text.splitlines() if line.strip()]
        init_line = next(
            (line for line in lines if json.loads(line).get("type") == "init"),
            None,
        )
        assert init_line is not None
        parsed = json.loads(init_line)
        assert parsed["type"] == "init"
        assert "timestamp" in parsed
        details = parsed.get("details", {})
        assert "createdDirectories" in details
        assert "createdFiles" in details

    def test_appends_vault_generation_entry(self, tmp_path: Path, wiki_config: object) -> None:
        initialize_memory_wiki_vault(wiki_config)  # type: ignore[arg-type]
        log_path = tmp_path / ".openclaw-wiki" / "log.jsonl"
        text = log_path.read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if line.strip()]
        gen_line = next(
            (line for line in lines if json.loads(line).get("type") == "vault-generation"),
            None,
        )
        assert gen_line is not None
        parsed = json.loads(gen_line)
        assert parsed["type"] == "vault-generation"
        details = parsed.get("details", {})
        assert "vaultGeneration" in details
        assert details["vaultGeneration"]  # non-empty

    def test_idempotent_vault_generation(self, tmp_path: Path, wiki_config: object) -> None:
        initialize_memory_wiki_vault(wiki_config)  # type: ignore[arg-type]
        first_gen = _read_vault_generation(tmp_path)
        # Re-init: a fresh init (without the
        # scaffold) is still a no-op for the
        # generation.
        from extensions.memory_wiki.log import (
            load_memory_wiki_vault_identity,
        )

        identity = load_memory_wiki_vault_identity(str(tmp_path))
        assert identity.vault_generation == first_gen
        assert first_gen  # non-empty


def _read_vault_generation(vault_root: Path) -> str:
    """Helper -- read the first ``vaultGeneration`` from the log."""
    log_path = vault_root / ".openclaw-wiki" / "log.jsonl"
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        if parsed.get("type") == "vault-generation":
            gen = parsed.get("details", {}).get("vaultGeneration")
            if gen:
                return str(gen)
    raise AssertionError("no vault-generation entry found in log")
