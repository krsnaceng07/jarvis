from __future__ import annotations

from pathlib import Path

from extensions.memory_core.runtime import MemoryRuntime


def test_search_text_uses_fts_index_for_term_matches(tmp_path: Path) -> None:
    runtime = MemoryRuntime(tmp_path / "memory.sqlite")
    runtime.set("alpha", "The quick brown fox jumps over the lazy dog")
    runtime.set("beta", "A separate note about winter planning")

    hits = runtime.search_text("quick brown", limit=5)

    assert any(hit["key"] == "alpha" for hit in hits)
    assert hits[0]["key"] == "alpha"


def test_rebuild_index_refreshes_fts_entries(tmp_path: Path) -> None:
    runtime = MemoryRuntime(tmp_path / "memory.sqlite")
    runtime.set("alpha", "Initial memory value")
    runtime.set("alpha", "Updated memory value with planning details")

    runtime.rebuild_index()
    hits = runtime.search_text("planning", limit=5)

    assert any(hit["key"] == "alpha" for hit in hits)
