"""jarvis_sdk.memory_host_internal_facade — public SDK re-export.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/memory-host-sdk/internal.ts``
(the SDK root facade that re-exports the public surface from
``host/internal.ts``).

The Python port re-exports the same public surface from
``jarvis_sdk.memory_host_internal``:
- ``hash_text`` (re-export of ``jarvis_sdk.memory_host_hash.hash_text``)
- ``ensure_dir`` / ``ensure_memory_host_dir``
- ``normalize_extra_memory_paths``
- ``is_memory_path``
- ``list_memory_files`` (async)
- ``build_file_entry`` (async)
- ``build_multimodal_chunk_for_indexing`` (async)
- ``chunk_markdown``
- ``remap_chunk_lines``
- ``parse_embedding``
- ``cosine_similarity``
- ``run_with_concurrency`` / ``run_memory_host_tasks_with_concurrency``
- ``MemoryFileEntry`` / ``MemoryChunk`` TypedDicts
"""
from __future__ import annotations

from .memory_host_hash import hash_text
from .memory_host_internal import (
    MEMORY_HOST_ROOT_FILENAME,
    MemoryChunk,
    MemoryFileEntry,
    build_file_entry,
    build_multimodal_chunk_for_indexing,
    chunk_markdown,
    cosine_similarity,
    ensure_dir,
    ensure_memory_host_dir,
    is_memory_path,
    list_memory_files,
    normalize_extra_memory_paths,
    parse_embedding,
    remap_chunk_lines,
    run_memory_host_tasks_with_concurrency,
    run_with_concurrency,
)

__all__ = [
    "hash_text",
    "MEMORY_HOST_ROOT_FILENAME",
    "MemoryFileEntry",
    "MemoryChunk",
    "ensure_dir",
    "ensure_memory_host_dir",
    "normalize_extra_memory_paths",
    "is_memory_path",
    "list_memory_files",
    "build_file_entry",
    "build_multimodal_chunk_for_indexing",
    "chunk_markdown",
    "remap_chunk_lines",
    "parse_embedding",
    "cosine_similarity",
    "run_with_concurrency",
    "run_memory_host_tasks_with_concurrency",
]
