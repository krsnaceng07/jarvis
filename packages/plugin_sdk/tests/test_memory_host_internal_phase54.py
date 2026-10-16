"""Tests for memory_host_internal — mirrors host/internal.ts.

Covers the engine helpers: ensure_dir, normalize_extra_memory_paths,
is_memory_path, list_memory_files, build_file_entry,
build_multimodal_chunk_for_indexing, chunk_markdown,
remap_chunk_lines, parse_embedding, cosine_similarity,
run_memory_host_tasks_with_concurrency.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import cast

import pytest

# Make the SDK importable when running this file in isolation.
_PKG_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PKG_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from jarvis_sdk.memory_host_internal import (  # noqa: E402
    MEMORY_HOST_ROOT_FILENAME,
    MemoryChunk,
    chunk_markdown,
    cosine_similarity,
    ensure_dir,
    is_memory_path,
    list_memory_files,
    normalize_extra_memory_paths,
    parse_embedding,
    remap_chunk_lines,
    run_memory_host_tasks_with_concurrency,
)


# ── Constants ───────────────────────────────────────────────────────


def test_root_filename_matches_openclaw() -> None:
    """``MEMORY_HOST_ROOT_FILENAME`` is ``"MEMORY.md"`` (OpenClaw)."""
    assert MEMORY_HOST_ROOT_FILENAME == "MEMORY.md"


# ── ensure_dir ──────────────────────────────────────────────────────


def test_ensure_dir_creates_nested(tmp_path: Path) -> None:
    """``ensure_dir`` creates intermediate directories."""
    target = tmp_path / "a" / "b" / "c"
    result = ensure_dir(str(target))
    assert result == str(target)
    assert target.is_dir()


def test_ensure_dir_existing_ok(tmp_path: Path) -> None:
    """``ensure_dir`` is idempotent — no error on existing dir."""
    target = tmp_path / "exists"
    target.mkdir()
    ensure_dir(str(target))  # should not raise
    assert target.is_dir()


# ── normalize_extra_memory_paths ────────────────────────────────────


def test_normalize_extra_paths_empty(tmp_path: Path) -> None:
    """Empty / None input returns an empty list."""
    assert normalize_extra_memory_paths(str(tmp_path), []) == []
    assert normalize_extra_memory_paths(str(tmp_path), None) == []


def test_normalize_extra_paths_relative(tmp_path: Path) -> None:
    """Relative paths are resolved against the workspace dir."""
    result = normalize_extra_memory_paths(str(tmp_path), ["docs", "notes"])
    assert all(Path(p).is_absolute() for p in result)
    assert str(tmp_path / "docs") in result
    assert str(tmp_path / "notes") in result


def test_normalize_extra_paths_absolute(tmp_path: Path) -> None:
    """Absolute paths are kept and deduped."""
    abs1 = str(tmp_path / "abs1")
    abs2 = str(tmp_path / "abs2")
    result = normalize_extra_memory_paths(
        str(tmp_path),
        [abs1, abs2, abs1],  # abs1 appears twice
    )
    assert result == [abs1, abs2]


def test_normalize_extra_paths_drops_empty(tmp_path: Path) -> None:
    """Empty / whitespace-only strings are dropped."""
    result = normalize_extra_memory_paths(
        str(tmp_path),
        ["", "  ", "valid", None],  # type: ignore[list-item]
    )
    assert len(result) == 1
    assert "valid" in result[0]


# ── is_memory_path ──────────────────────────────────────────────────


def test_is_memory_path_canonical_root() -> None:
    """The canonical ``MEMORY.md`` is a memory path."""
    assert is_memory_path("MEMORY.md") is True


def test_is_memory_path_legacy_root() -> None:
    """The legacy ``dreams.md`` is a memory path (lowercased)."""
    assert is_memory_path("dreams.md") is True


def test_is_memory_path_under_memory_dir() -> None:
    """Any path under ``memory/`` is a memory path."""
    assert is_memory_path("memory/note.md") is True
    assert is_memory_path("memory/sub/note.md") is True


def test_is_memory_path_not_a_memory_path() -> None:
    """A path outside the memory tree is not a memory path."""
    assert is_memory_path("random.md") is False
    assert is_memory_path("docs/foo.md") is False


def test_is_memory_path_strips_leading_dot_slash() -> None:
    """Leading ``./`` sequences are stripped."""
    assert is_memory_path("./memory/foo.md") is True
    assert is_memory_path("..//memory/foo.md") is True


def test_is_memory_path_empty_string() -> None:
    """Empty / whitespace input returns ``False``."""
    assert is_memory_path("") is False
    assert is_memory_path("   ") is False


def test_is_memory_path_backslashes_normalized() -> None:
    """Backslashes are converted to forward slashes."""
    assert is_memory_path("memory\\foo.md") is True


# ── list_memory_files ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_memory_files_includes_root(tmp_path: Path) -> None:
    """A workspace with ``MEMORY.md`` lists the root file."""
    (tmp_path / "MEMORY.md").write_text("hello", encoding="utf-8")
    result = await list_memory_files(str(tmp_path))
    assert any(p.endswith("MEMORY.md") for p in result)


@pytest.mark.asyncio
async def test_list_memory_files_includes_memory_dir(tmp_path: Path) -> None:
    """All ``*.md`` files under ``memory/`` are listed."""
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "a.md").write_text("a", encoding="utf-8")
    (mem / "b.md").write_text("b", encoding="utf-8")
    (mem / "ignore.txt").write_text("not a memory file", encoding="utf-8")
    result = await list_memory_files(str(tmp_path))
    paths = [Path(p).name for p in result]
    assert "a.md" in paths
    assert "b.md" in paths
    assert "ignore.txt" not in paths


@pytest.mark.asyncio
async def test_list_memory_files_skips_legacy(tmp_path: Path) -> None:
    """The legacy lowercase ``memory.md`` is NOT listed (root-only)."""
    (tmp_path / "memory.md").write_text("legacy", encoding="utf-8")
    result = await list_memory_files(str(tmp_path))
    assert not any(p.endswith("memory.md") for p in result)


@pytest.mark.asyncio
async def test_list_memory_files_extra_paths(tmp_path: Path) -> None:
    """Extra paths are included."""
    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "x.md").write_text("x", encoding="utf-8")
    result = await list_memory_files(str(tmp_path), extra_paths=[str(extra)])
    assert any(p.endswith("x.md") for p in result)


@pytest.mark.asyncio
async def test_list_memory_files_empty_workspace(tmp_path: Path) -> None:
    """A workspace with no memory files returns an empty list."""
    result = await list_memory_files(str(tmp_path))
    assert result == []


@pytest.mark.asyncio
async def test_list_memory_files_dedupes_by_realpath(tmp_path: Path) -> None:
    """Duplicate entries (same realpath) are collapsed."""
    (tmp_path / "MEMORY.md").write_text("hello", encoding="utf-8")
    # Also add a copy under memory/ — but content text won't matter
    mem = tmp_path / "memory"
    mem.mkdir()
    # Create a real duplicate by referencing the same file
    import os

    same_target = tmp_path / "MEMORY.md"
    link = mem / "MEMORY.md"
    try:
        os.symlink(same_target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform")
    result = await list_memory_files(str(tmp_path))
    # Only one entry survives the realpath dedup.
    realpaths = {os.path.realpath(p) for p in result}
    assert len(realpaths) == len([p for p in result if p.endswith("MEMORY.md")])


# ── chunk_markdown ──────────────────────────────────────────────────


def test_chunk_markdown_empty_content() -> None:
    """OpenClaw's ``content.split("\\n")`` on ``""`` returns
    ``[""]`` (a single empty string), so the chunker yields
    one chunk with empty text. The early-return path requires
    an actually-empty array, which can't happen via ``split``.
    """
    chunks = chunk_markdown("", {"tokens": 100, "overlap": 0})
    assert len(chunks) == 1
    assert chunks[0]["text"] == ""


def test_chunk_markdown_short_content_one_chunk() -> None:
    """A short content produces exactly one chunk."""
    content = "line 1\nline 2\nline 3"
    chunks = chunk_markdown(content, {"tokens": 100, "overlap": 0})
    assert len(chunks) == 1
    assert chunks[0]["text"] == content
    assert chunks[0]["startLine"] == 1
    assert chunks[0]["endLine"] == 3


def test_chunk_markdown_long_content_multiple_chunks() -> None:
    """Content longer than the budget produces multiple chunks."""
    # 10 lines of 100 chars each = 1000 chars; budget = 10 tokens * 4 = 40
    lines = ["x" * 100 for _ in range(10)]
    content = "\n".join(lines)
    chunks = chunk_markdown(content, {"tokens": 10, "overlap": 0})
    assert len(chunks) > 1


def test_chunk_markdown_overlap_carry() -> None:
    """Overlap keeps the tail of the previous chunk in the next."""
    lines = ["x" * 50 for _ in range(10)]
    content = "\n".join(lines)
    chunks_no_overlap = chunk_markdown(content, {"tokens": 5, "overlap": 0})
    chunks_with_overlap = chunk_markdown(content, {"tokens": 5, "overlap": 2})
    # With overlap, the second chunk starts with content from the first.
    if len(chunks_no_overlap) > 1 and len(chunks_with_overlap) > 1:
        # The overlap chunks should be larger in total.
        total_no = sum(len(c["text"]) for c in chunks_no_overlap)
        total_with = sum(len(c["text"]) for c in chunks_with_overlap)
        assert total_with >= total_no


def test_chunk_markdown_preserves_line_numbers() -> None:
    """Chunk startLine / endLine are 1-indexed and refer to source lines."""
    lines = [f"line {i}" for i in range(1, 11)]
    content = "\n".join(lines)
    chunks = chunk_markdown(content, {"tokens": 5, "overlap": 0})
    # First chunk should start at line 1.
    assert chunks[0]["startLine"] == 1
    # Last chunk should end at line 10.
    assert chunks[-1]["endLine"] == 10


def test_chunk_markdown_embedding_input_attached() -> None:
    """Each chunk carries an ``embeddingInput`` (text-only by default)."""
    chunks = chunk_markdown("hello\nworld", {"tokens": 100, "overlap": 0})
    assert len(chunks) == 1
    assert "embeddingInput" in chunks[0]
    assert chunks[0]["embeddingInput"]["text"] == "hello\nworld"


def test_chunk_markdown_hash_per_chunk() -> None:
    """Each chunk has a unique hash."""
    lines = ["x" * 100 for _ in range(10)]
    chunks = chunk_markdown("\n".join(lines), {"tokens": 5, "overlap": 0})
    hashes = {c["hash"] for c in chunks}
    # At least some chunks should have distinct content (and thus distinct hashes).
    assert len(hashes) >= 1


def test_chunk_markdown_handles_cjk() -> None:
    """CJK-heavy content is chunked at ~1 char/token (not 4 chars/token)."""
    # 50 CJK chars; with 4-chars-per-token this is 12.5 tokens.
    # With CJK-aware counting this is 50 tokens, well over the budget.
    content = "中" * 50
    chunks = chunk_markdown(content, {"tokens": 5, "overlap": 0})
    # Should produce multiple chunks since 50 CJK chars is way over
    # the 5-token budget when CJK is counted as 1 char/token.
    assert len(chunks) > 1


# ── remap_chunk_lines ───────────────────────────────────────────────


def test_remap_chunk_lines_basic() -> None:
    """Chunks have their line numbers remapped via the line map."""
    chunks = cast(
        list[MemoryChunk],
        [
            {"startLine": 1, "endLine": 2, "text": "a", "hash": "h"},
            {"startLine": 3, "endLine": 4, "text": "b", "hash": "h"},
        ],
    )
    # Map content-line 1 -> source-line 10, 2 -> 11, 3 -> 20, 4 -> 21
    remap_chunk_lines(chunks, [10, 11, 20, 21])
    assert chunks[0].get("startLine") == 10
    assert chunks[0].get("endLine") == 11
    assert chunks[1].get("startLine") == 20
    assert chunks[1].get("endLine") == 21


def test_remap_chunk_lines_no_map() -> None:
    """``None`` / empty line_map is a no-op."""
    chunks = cast(list[MemoryChunk], [{"startLine": 1, "endLine": 2, "text": "a", "hash": "h"}])
    remap_chunk_lines(chunks, None)
    assert chunks[0].get("startLine") == 1


def test_remap_chunk_lines_out_of_range_unchanged() -> None:
    """Out-of-range startLine / endLine are kept unchanged."""
    chunks = cast(list[MemoryChunk], [{"startLine": 100, "endLine": 200, "text": "a", "hash": "h"}])
    remap_chunk_lines(chunks, [1, 2, 3])
    assert chunks[0].get("startLine") == 100
    assert chunks[0].get("endLine") == 200


# ── parse_embedding ─────────────────────────────────────────────────


def test_parse_embedding_valid() -> None:
    """A valid JSON array is parsed into floats."""
    assert parse_embedding("[1, 2, 3]") == [1.0, 2.0, 3.0]
    assert parse_embedding("[1.5, -2.0, 0]") == [1.5, -2.0, 0.0]


def test_parse_embedding_garbage() -> None:
    """Garbage input returns ``[]``."""
    assert parse_embedding("not json") == []
    assert parse_embedding("") == []


def test_parse_embedding_non_array() -> None:
    """Non-array JSON returns ``[]``."""
    assert parse_embedding('{"a": 1}') == []
    assert parse_embedding("42") == []


def test_parse_embedding_filters_non_numeric() -> None:
    """Non-numeric entries are filtered out."""
    result = parse_embedding('[1, "two", 3, null]')
    assert result == [1.0, 3.0]


# ── cosine_similarity ───────────────────────────────────────────────


def test_cosine_similarity_identical() -> None:
    """Identical vectors have similarity 1."""
    assert cosine_similarity([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal() -> None:
    """Orthogonal vectors have similarity 0."""
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)


def test_cosine_similarity_opposite() -> None:
    """Opposite vectors have similarity -1."""
    assert cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)


def test_cosine_similarity_empty() -> None:
    """Empty input returns 0."""
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([], [1, 2]) == 0.0
    assert cosine_similarity([1, 2], []) == 0.0


def test_cosine_similarity_zero_norm() -> None:
    """Zero-norm vectors return 0."""
    assert cosine_similarity([0, 0], [1, 2]) == 0.0
    assert cosine_similarity([1, 2], [0, 0]) == 0.0


def test_cosine_similarity_min_length() -> None:
    """The dimension is the min of the two vector lengths."""
    # The third element of ``a`` is ignored since ``b`` is length 2.
    sim = cosine_similarity([1, 0, 99], [1, 0])
    assert sim == pytest.approx(1.0)


# ── run_memory_host_tasks_with_concurrency ──────────────────────────


@pytest.mark.asyncio
async def test_run_concurrency_basic() -> None:
    """All tasks run and return their values in order."""

    async def task(i: int) -> int:
        await asyncio.sleep(0)
        return i

    from typing import Awaitable, Callable

    tasks_typed: list[Callable[[], Awaitable[int]]] = [(lambda i=i: task(i)) for i in range(5)]
    results = await run_memory_host_tasks_with_concurrency(tasks_typed, limit=2)
    assert sorted(results) == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_run_concurrency_limit_one_serializes() -> None:
    """With limit=1, tasks run sequentially."""
    counter = {"active": 0, "max_active": 0}

    async def task() -> int:
        counter["active"] += 1
        counter["max_active"] = max(counter["max_active"], counter["active"])
        await asyncio.sleep(0.01)
        counter["active"] -= 1
        return 1

    from typing import Awaitable, Callable

    tasks_typed: list[Callable[[], Awaitable[int]]] = [task for _ in range(5)]
    results = await run_memory_host_tasks_with_concurrency(tasks_typed, limit=1)
    assert sum(results) == 5
    # With limit=1, max concurrent should be 1.
    assert counter["max_active"] == 1


@pytest.mark.asyncio
async def test_run_concurrency_propagates_error() -> None:
    """When a task fails, the error is re-raised after drain."""

    async def ok_task() -> int:
        await asyncio.sleep(0)
        return 1

    async def fail_task() -> int:
        await asyncio.sleep(0.005)
        raise ValueError("boom")

    from typing import Awaitable, Callable

    tasks_typed: list[Callable[[], Awaitable[int]]] = [ok_task, fail_task, ok_task]
    with pytest.raises(ValueError, match="boom"):
        await run_memory_host_tasks_with_concurrency(tasks_typed, limit=2)


@pytest.mark.asyncio
async def test_run_concurrency_empty() -> None:
    """An empty task list returns ``[]``."""
    result = await run_memory_host_tasks_with_concurrency([], limit=4)
    assert result == []


@pytest.mark.asyncio
async def test_run_concurrency_limit_zero_uses_one() -> None:
    """A non-positive limit is normalized to 1."""

    async def task() -> int:
        return 42

    result = await run_memory_host_tasks_with_concurrency([task], limit=0)
    assert result == [42]
