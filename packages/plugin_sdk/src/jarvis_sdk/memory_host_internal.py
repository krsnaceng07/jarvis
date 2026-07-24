"""jarvis_sdk.memory_host_internal — internal memory host engine helpers.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/internal.ts`` (~550 LOC).
The engine layer for the memory host: directory walking,
file-entry construction, multimodal indexing input, markdown
chunking, embedding-parse + cosine similarity, and bounded
task concurrency.

Public API:
- ``ensure_dir`` / ``ensure_memory_host_dir`` — mkdir -p the
  given directory.
- ``normalize_extra_memory_paths(workspace_dir, extra_paths)``
  — resolve and dedup extra memory roots (with ``~``
  expansion).
- ``is_memory_path(rel_path)`` — true for the canonical
  memory file names (``MEMORY.md`` / ``memory/...``).
- ``list_memory_files(workspace_dir, extra_paths, multimodal)``
  — async; collect all indexable memory files in the
  workspace + extra paths.
- ``build_file_entry(abs_path, workspace_dir, multimodal)``
  — async; build a ``MemoryFileEntry`` for a single file
  (markdown or multimodal).
- ``build_multimodal_chunk_for_indexing(entry)`` — async;
  build a structured embedding input for a multimodal entry.
- ``chunk_markdown(content, chunking)`` — split markdown
  content into token-bounded chunks with overlap.
- ``remap_chunk_lines(chunks, line_map)`` — remap chunk
  line numbers via an explicit line map.
- ``parse_embedding(raw)`` — JSON-parse an embedding vector.
- ``cosine_similarity(a, b)`` — cosine similarity between
  two vectors.
- ``run_with_concurrency`` / ``run_memory_host_tasks_with_concurrency``
  — bounded-concurrency task runner.
- ``hash_text`` (re-export from ``memory_host_hash``).

Key port decisions:
- All IO goes through the ``memory_host_fs_utils`` shim
  (port of ``@openclaw/fs-safe``) so the engine never reads
  through a symlink by accident.
- ``chunk_markdown`` uses ``CHARS_PER_TOKEN_ESTIMATE`` from
  the CJK-aware ``memory_host_cjk_chars`` helper so CJK-heavy
  markdown is chunked accurately.
- ``is_memory_path`` accepts both ``memory/foo`` and
  ``memory.md`` paths (the latter is the legacy root memory
  filename excluded from auxiliary scans by the
  ``should_skip_root_memory_auxiliary_path`` predicate).
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from .memory_host_cjk_chars import CHARS_PER_TOKEN_ESTIMATE, estimate_string_chars
from .memory_host_concurrency import run_with_concurrency
from .memory_host_embedding_input_limits import (
    estimate_structured_embedding_input_bytes,
)
from .memory_host_embedding_inputs import (
    EmbeddingInput,
    build_text_embedding_input,
)
from .memory_host_fs_utils import (
    is_file_missing_error,
    read_regular_file,
    stat_regular_file,
    walk_directory,
)
from .memory_host_hash import hash_text
from .memory_host_multimodal import (
    MemoryMultimodalModality,
    MemoryMultimodalSettings,
    build_memory_multimodal_label,
    classify_memory_multimodal_path,
    normalize_memory_multimodal_settings,
)
from .memory_host_read_retry import retry_transient_memory_read
from .memory_host_runtime_io import detect_mime, truncate_utf16_safe
from .memory_host_runtime_memory import (
    CANONICAL_ROOT_MEMORY_FILENAME as _CANONICAL_ROOT_MEMORY_FILENAME,
    resolve_canonical_root_memory_file,
    should_skip_root_memory_auxiliary_path,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

# Re-export ``hash_text`` for callers that import from the
# internal facade (mirrors the ``export { hashText }`` line in
# the OpenClaw source).
__all__ = [
    "hash_text",
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
    "MemoryFileEntry",
    "MemoryChunk",
]


class MemoryFileEntry(TypedDict, total=False):
    """One memory-file entry produced by the indexer.

    Mirrors OpenClaw's ``MemoryFileEntry`` type.
    """

    path: str
    absPath: str  # noqa: N815 — camelCase mirrors OpenClaw JSON
    mtimeMs: float  # noqa: N815
    size: int
    hash: str
    dataHash: str  # noqa: N815
    kind: Literal["markdown", "multimodal"]
    contentText: str  # noqa: N815
    modality: MemoryMultimodalModality
    mimeType: str  # noqa: N815


class MemoryChunk(TypedDict, total=False):
    """One chunk produced by ``chunk_markdown``.

    Mirrors OpenClaw's ``MemoryChunk`` type.
    """

    startLine: int  # noqa: N815
    endLine: int  # noqa: N815
    text: str
    hash: str
    embeddingInput: EmbeddingInput  # noqa: N815


# Register the ``from`` field on MemoryChunk after the class
# body — ``from`` is a Python keyword.
MemoryChunk.__annotations__["from"] = int  # type: ignore[attr-defined]


# Mirrors OpenClaw's ``DISABLED_MULTIMODAL_SETTINGS``. Used
# as a fallback when callers don't pass ``multimodal``.
_DISABLED_MULTIMODAL_SETTINGS: MemoryMultimodalSettings = {
    "enabled": False,
    "modalities": [],
    "maxFileBytes": 0,
}

# Mirrors OpenClaw's ``MEMORY_HOST_ROOT_FILENAME`` from
# ``config-utils.ts``. The canonical root memory file name.
MEMORY_HOST_ROOT_FILENAME: str = _CANONICAL_ROOT_MEMORY_FILENAME

# Mirrors OpenClaw's ``normalizeStringEntries`` (drops
# empties + de-dups preserving order).
def _normalize_string_entries(values: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        if not isinstance(value, str):
            continue
        trimmed = value.strip()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        out.append(trimmed)
    return out


def _unique_strings(values: list[str]) -> list[str]:
    """De-dup a list of strings preserving first-occurrence order."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def ensure_memory_host_dir(dir_path: str) -> str:
    """Recursively create ``dir_path`` and return it.

    Mirrors OpenClaw's ``ensureMemoryHostDir``. Uses
    ``os.makedirs(..., exist_ok=True)`` for the create-if-
    missing semantics.
    """
    os.makedirs(dir_path, exist_ok=True)
    return dir_path


# Public alias — mirrors OpenClaw's ``export { ensureMemoryHostDir as ensureDir }``.
ensure_dir = ensure_memory_host_dir


def _normalize_rel_path(value: str) -> str:
    """Normalize a memory-relative path.

    Mirrors OpenClaw's ``normalizeRelPath``:
    1. ``trim()``
    2. Drop leading ``./`` sequences
    3. Swap backslashes for forward slashes
    """
    trimmed = value.strip().lstrip("./").lstrip(".\\")
    # Repeat the lstrip until no more leading ``./`` (in case of
    # ``..//foo`` shapes).
    while trimmed.startswith("./") or trimmed.startswith(".\\"):
        trimmed = trimmed[2:]
    return trimmed.replace("\\", "/")


def _expand_home_path(value: str) -> str:
    """Expand a leading ``~`` to the user's home directory.

    Mirrors OpenClaw's ``expandHomePath``. ``~`` alone maps
    to the home directory; ``~/foo`` and ``~\\foo`` map to
    ``<home>/foo``. ``~user/...`` is not expanded (we use
    ``os.path.expanduser`` semantics here, which actually
    does support ``~user`` on POSIX; OpenClaw's TS version
    only handles the leading ``~`` and ``~/`` forms).
    """
    if value == "~":
        return os.path.expanduser("~")
    if value.startswith("~/") or value.startswith("~\\"):
        return os.path.join(os.path.expanduser("~"), value[2:])
    return value


def normalize_extra_memory_paths(
    workspace_dir: str,
    extra_paths: list[str] | None = None,
) -> list[str]:
    """Normalize and dedup extra memory paths for a workspace.

    Mirrors OpenClaw's ``normalizeExtraMemoryPaths``. Each
    path is home-expanded, then resolved (absolute paths
    resolved against ``workspace_dir`` if relative). Returns
    a de-duplicated list preserving insertion order.
    """
    if not extra_paths:
        return []
    resolved = _normalize_string_entries(extra_paths)
    resolved = [_expand_home_path(value) for value in resolved]
    resolved = [
        os.path.abspath(value) if os.path.isabs(value) else os.path.abspath(
            os.path.join(workspace_dir, value)
        )
        for value in resolved
    ]
    return _unique_strings(resolved)


def is_memory_path(rel_path: str) -> bool:
    """True when ``rel_path`` is an indexable memory file.

    Mirrors OpenClaw's ``isMemoryPath``. The canonical root
    memory file (``MEMORY.md``) and the legacy lowercase
    ``memory.md`` are both indexable. Any other file under
    the ``memory/`` directory is also indexable.
    """
    normalized = _normalize_rel_path(rel_path)
    if not normalized:
        return False
    if normalized == MEMORY_HOST_ROOT_FILENAME or normalized.lower() == "dreams.md":
        return True
    return normalized.startswith("memory/")


def _is_allowed_memory_file_path(
    file_path: str,
    multimodal: MemoryMultimodalSettings | None = None,
) -> bool:
    """True when ``file_path`` is an indexable memory file by extension.

    Mirrors OpenClaw's ``isAllowedMemoryFilePath``. Markdown
    files (``*.md``) are always allowed. Other extensions
    are checked against the multimodal spec.
    """
    if file_path.endswith(".md"):
        return True
    settings = multimodal or _DISABLED_MULTIMODAL_SETTINGS
    return classify_memory_multimodal_path(file_path, settings) is not None


def _should_descend_memory_entry(
    entry: dict[str, Any],
    should_skip_path: Callable[[str], bool] | None = None,
) -> bool:
    """Whether to descend into a directory during a memory walk.

    Mirrors OpenClaw's ``shouldDescendMemoryEntry``. The
    ``.openclaw-repair`` directory is always skipped.
    """
    if should_skip_path and should_skip_path(entry["path"]):
        return False
    return entry.get("kind") == "directory" and entry.get("name") != ".openclaw-repair"


async def _collect_memory_files_from_dir(
    dir_path: str,
    files: list[str],
    multimodal: MemoryMultimodalSettings | None = None,
    should_skip_path: Callable[[str], bool] | None = None,
) -> None:
    """Collect memory file paths under ``dir_path`` into ``files``.

    Mirrors OpenClaw's ``collectMemoryFilesFromDir``. Uses
    ``walk_directory`` with the standard descent + include
    filters.
    """
    scan = walk_directory(
        dir_path,
        {
            "symlinks": "skip",
            "descend": lambda entry: _should_descend_memory_entry(entry, should_skip_path),
            "include": lambda entry: (
                should_skip_path is None
                or not should_skip_path(entry["path"])
            )
            and entry.get("kind") == "file"
            and _is_allowed_memory_file_path(entry["path"], multimodal),
        },
    )
    for entry in scan["entries"]:
        files.append(entry["path"])


async def list_memory_files(
    workspace_dir: str,
    extra_paths: list[str] | None = None,
    multimodal: MemoryMultimodalSettings | None = None,
) -> list[str]:
    """List all indexable memory files in the workspace + extra paths.

    Mirrors OpenClaw's ``listMemoryFiles``. Always includes
    the canonical root memory file (when present), all files
    under the ``memory/`` directory, and any markdown /
    multimodal files under the configured extra paths.
    Dedupes by realpath when multiple results map to the
    same file.
    """
    result: list[str] = []
    memory_dir = os.path.join(workspace_dir, "memory")
    settings = normalize_memory_multimodal_settings(multimodal or None)

    def should_skip_workspace_memory_path(abs_path: str) -> bool:
        return should_skip_root_memory_auxiliary_path(workspace_dir, abs_path)

    async def add_markdown_file(abs_path: str) -> None:
        try:
            stat_result = stat_regular_file(abs_path)
            if stat_result["missing"]:
                return
            if not abs_path.endswith(".md"):
                return
            result.append(abs_path)
        except Exception:  # noqa: BLE001 — match OpenClaw's catch-all
            return

    # 1. Canonical root memory file (MEMORY.md).
    memory_file = await resolve_canonical_root_memory_file(workspace_dir)
    if memory_file:
        await add_markdown_file(memory_file)

    # 2. Walk the ``memory/`` directory.
    try:
        if not os.path.islink(memory_dir) and os.path.isdir(memory_dir):
            await _collect_memory_files_from_dir(
                memory_dir, result, settings, should_skip_workspace_memory_path
            )
    except OSError:
        pass

    # 3. Walk the configured extra paths.
    normalized_extra_paths = normalize_extra_memory_paths(workspace_dir, extra_paths)
    if normalized_extra_paths:
        for input_path in normalized_extra_paths:
            if should_skip_workspace_memory_path(input_path):
                continue
            try:
                os.lstat(input_path)
            except OSError:
                continue
            if os.path.islink(input_path):
                continue
            if os.path.isdir(input_path):
                await _collect_memory_files_from_dir(
                    input_path, result, settings, should_skip_workspace_memory_path
                )
                continue
            if os.path.isfile(input_path) and _is_allowed_memory_file_path(input_path, settings):
                result.append(input_path)

    # 4. Dedupe by realpath when we have more than one entry.
    if len(result) <= 1:
        return result
    seen: set[str] = set()
    deduped: list[str] = []
    for entry in result:
        key = entry
        try:
            key = os.path.realpath(entry)
        except OSError:
            pass
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def _sha256_hex(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


async def build_file_entry(
    abs_path: str,
    workspace_dir: str,
    multimodal: MemoryMultimodalSettings | None = None,
) -> MemoryFileEntry | None:
    """Build a ``MemoryFileEntry`` for a single memory file.

    Mirrors OpenClaw's ``buildFileEntry``. Returns ``None``
    when the file is missing, when it's a multimodal file
    that exceeds the size cap, or when its MIME type doesn't
    match the expected modality prefix.
    """
    settings = normalize_memory_multimodal_settings(multimodal)
    regular_file = stat_regular_file(abs_path)
    if regular_file["missing"]:
        return None
    stat = regular_file["stat"]
    if stat is None:
        return None
    normalized_path = os.path.relpath(abs_path, workspace_dir).replace("\\", "/")
    modality = classify_memory_multimodal_path(abs_path, settings)
    if modality:
        # Multimodal branch.
        if stat.st_size > settings["maxFileBytes"]:
            return None

        async def _do_read_multimodal() -> dict:
            return read_regular_file(
                file_path=abs_path, max_bytes=settings["maxFileBytes"]
            )

        try:
            read_result = await retry_transient_memory_read(
                _do_read_multimodal,
                f"read multimodal memory file {abs_path}",
            )
        except Exception as err:  # noqa: BLE001
            if is_file_missing_error(err):
                return None
            raise
        buffer = read_result["buffer"]
        mime_type = detect_mime(buffer=buffer[:512], file_path=abs_path)
        if not mime_type or not mime_type.startswith(f"{modality}/"):
            return None
        content_text = build_memory_multimodal_label(modality, normalized_path)
        data_hash = _sha256_hex(buffer)
        chunk_hash = hash_text(
            json.dumps(
                {
                    "path": normalized_path,
                    "contentText": content_text,
                    "mimeType": mime_type,
                    "dataHash": data_hash,
                }
            )
        )
        return {
            "path": normalized_path,
            "absPath": abs_path,
            "mtimeMs": stat.st_mtime,
            "size": stat.st_size,
            "hash": chunk_hash,
            "dataHash": data_hash,
            "kind": "multimodal",
            "contentText": content_text,
            "modality": modality,
            "mimeType": mime_type,
        }
    # Markdown branch.

    async def _do_read_markdown() -> dict:
        return read_regular_file(file_path=abs_path)

    try:
        read_result = await retry_transient_memory_read(
            _do_read_markdown,
            f"read memory index file {abs_path}",
        )
    except Exception as err:  # noqa: BLE001
        if is_file_missing_error(err):
            return None
        raise
    content = read_result["buffer"].decode("utf-8")
    return {
        "path": normalized_path,
        "absPath": abs_path,
        "mtimeMs": stat.st_mtime,
        "size": stat.st_size,
        "hash": hash_text(content),
        "kind": "markdown",
    }


async def _load_multimodal_embedding_input(
    entry: MemoryFileEntry,
) -> EmbeddingInput | None:
    """Build a structured embedding input for a multimodal entry.

    Mirrors OpenClaw's ``loadMultimodalEmbeddingInput``.
    Returns ``None`` when the entry is not multimodal, when
    the file is missing / changed since the entry was
    built, or when the data hash doesn't match the entry's.
    """
    if (
        entry.get("kind") != "multimodal"
        or not entry.get("contentText")
        or not entry.get("mimeType")
    ):
        return None
    abs_path = entry.get("absPath", "")
    if not abs_path:
        return None
    regular_file = stat_regular_file(abs_path)
    if regular_file["missing"]:
        return None
    stat = regular_file["stat"]
    if stat is None or stat.st_size != entry.get("size"):
        return None
    try:

        async def _do_read() -> dict:
            return read_regular_file(file_path=abs_path, max_bytes=entry["size"])

        read_result = await retry_transient_memory_read(
            _do_read,
            f"read multimodal indexing file {abs_path}",
        )
    except Exception as err:  # noqa: BLE001
        if is_file_missing_error(err):
            return None
        raise
    buffer = read_result["buffer"]
    data_hash = _sha256_hex(buffer)
    entry_data_hash = entry.get("dataHash")
    if entry_data_hash and entry_data_hash != data_hash:
        return None
    mime_type = entry["mimeType"]
    content_text = entry["contentText"]
    return {
        "text": content_text,
        "parts": [
            {"type": "text", "text": content_text},
            {"type": "inline-data", "mimeType": mime_type, "data": buffer.decode("latin-1")},
        ],
    }


async def build_multimodal_chunk_for_indexing(
    entry: MemoryFileEntry,
) -> dict[str, Any] | None:
    """Build a ``MultimodalMemoryChunk`` for a multimodal entry.

    Mirrors OpenClaw's ``buildMultimodalChunkForIndexing``.
    Returns ``None`` when the entry isn't a valid multimodal
    entry (missing file, changed size, mismatched data hash).
    """
    embedding_input = await _load_multimodal_embedding_input(entry)
    if not embedding_input:
        return None
    return {
        "chunk": {
            "startLine": 1,
            "endLine": 1,
            "text": entry.get("contentText", embedding_input["text"]),
            "hash": entry.get("hash", ""),
            "embeddingInput": embedding_input,
        },
        "structuredInputBytes": estimate_structured_embedding_input_bytes(embedding_input),
    }


def chunk_markdown(
    content: str,
    chunking: dict[str, int],
) -> list[MemoryChunk]:
    """Split markdown content into token-bounded chunks with overlap.

    Mirrors OpenClaw's ``chunkMarkdown``. The chunking budget
    is expressed in tokens; the function converts to chars
    via ``CHARS_PER_TOKEN_ESTIMATE`` and the CJK-aware
    ``estimateStringChars`` helper, so CJK-heavy content is
    chunked at ~1 char/token instead of the Latin
    1 token / 4 chars.
    """
    lines = content.split("\n")
    if not lines:
        return []
    max_chars = max(32, int(chunking["tokens"]) * CHARS_PER_TOKEN_ESTIMATE)
    overlap_chars = max(0, int(chunking["overlap"]) * CHARS_PER_TOKEN_ESTIMATE)
    chunks: list[MemoryChunk] = []
    current: list[dict[str, Any]] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        first = current[0]
        last = current[-1]
        if not first or not last:
            return
        text = "\n".join(entry["line"] for entry in current)
        chunks.append(
            {
                "startLine": first["lineNo"],
                "endLine": last["lineNo"],
                "text": text,
                "hash": hash_text(text),
                "embeddingInput": build_text_embedding_input(text),
            }
        )

    def carry_overlap() -> None:
        nonlocal current, current_chars
        if overlap_chars <= 0 or not current:
            current = []
            current_chars = 0
            return
        acc = 0
        kept: list[dict[str, Any]] = []
        for i in range(len(current) - 1, -1, -1):
            entry = current[i]
            if not entry:
                continue
            acc += estimate_string_chars(entry["line"]) + 1
            kept.insert(0, entry)
            if acc >= overlap_chars:
                break
        current = kept
        current_chars = acc

    for i, raw_line in enumerate(lines):
        line = raw_line or ""
        line_no = i + 1
        segments: list[str] = []
        if len(line) == 0:
            segments.append("")
        else:
            start = 0
            while start < len(line):
                coarse = truncate_utf16_safe(line[start:], max_chars)
                if estimate_string_chars(coarse) > max_chars:
                    fine_step = max(1, int(chunking["tokens"]))
                    j = 0
                    while j < len(coarse):
                        end = min(j + fine_step, len(coarse))
                        # Avoid splitting a surrogate pair.
                        last_code = ord(coarse[end - 1])
                        if 0xD800 <= last_code <= 0xDBFF and end < len(coarse):
                            end += 1
                        segments.append(coarse[j:end])
                        j = end
                else:
                    segments.append(coarse)
                start += len(coarse)
        for segment in segments:
            line_size = estimate_string_chars(segment) + 1
            if current_chars + line_size > max_chars and current:
                flush()
                carry_overlap()
            current.append({"line": segment, "lineNo": line_no})
            current_chars += line_size
    flush()
    return chunks


def remap_chunk_lines(
    chunks: list[MemoryChunk],
    line_map: list[int] | None,
) -> None:
    """Remap chunk startLine/endLine via an explicit line map.

    Mirrors OpenClaw's ``remapChunkLines``. Used for
    session JSONL files where the chunker sees a flattened
    text representation; the line map lets us translate
    back to original source file positions.
    """
    if not line_map:
        return
    for chunk in chunks:
        start = chunk.get("startLine", 1)
        end = chunk.get("endLine", 1)
        if 0 < start <= len(line_map):
            chunk["startLine"] = line_map[start - 1]
        if 0 < end <= len(line_map):
            chunk["endLine"] = line_map[end - 1]


def parse_embedding(raw: str) -> list[float]:
    """Parse a JSON-encoded embedding vector.

    Mirrors OpenClaw's ``parseEmbedding``. Returns ``[]`` on
    any parse error or non-array result.
    """
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    out: list[float] = []
    for value in parsed:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out.append(float(value))
    return out


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors.

    Mirrors OpenClaw's ``cosineSimilarity``. Returns ``0``
    when either vector is empty or has zero norm. The
    dimension is the min of ``len(a)`` and ``len(b)``.
    """
    if not a or not b:
        return 0.0
    length = min(len(a), len(b))
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for i in range(length):
        av = float(a[i]) if i < len(a) else 0.0
        bv = float(b[i]) if i < len(b) else 0.0
        dot += av * bv
        norm_a += av * av
        norm_b += bv * bv
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / ((norm_a**0.5) * (norm_b**0.5))


# Mirrors OpenClaw's ``runMemoryHostTasksWithConcurrency``.
async def run_memory_host_tasks_with_concurrency(
    tasks: list[Callable[[], Awaitable[Any]]],
    limit: int,
) -> list[Any]:
    return await run_with_concurrency(tasks, limit)
