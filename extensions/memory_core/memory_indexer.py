from pathlib import Path
from typing import List

# Try to import jarvis' text chunking if available, otherwise fallback to simple chunker
try:
    from src.shared.text_chunking import chunk_text_by_break_resolver
except ImportError:
    # A simplified version if not found
    import math
    import re

    _WS_RE = re.compile(r"\s")

    def avoid_trailing_high_surrogate_break(text: str, _start: int, end: int) -> int:
        if end <= 0 or end >= len(text):
            return end
        if (
            0xD800 <= ord(text[end - 1]) <= 0xDBFF
            and end < len(text)
            and 0xDC00 <= ord(text[end]) <= 0xDFFF
        ):
            return end - 1
        return end

    def chunk_text_by_break_resolver(text: str, limit: int, resolve_break_index) -> List[str]:
        if not text:
            return []
        if limit <= 0 or len(text) <= limit:
            return [text]
        chunks = []
        remaining = text
        while len(remaining) > limit:
            window = remaining[:limit]
            candidate = resolve_break_index(window)
            break_idx = (
                int(candidate)
                if (
                    isinstance(candidate, (int, float))
                    and math.isfinite(candidate)
                    and 0 < candidate <= limit
                )
                else limit
            )
            safe_break_idx = avoid_trailing_high_surrogate_break(remaining, 0, break_idx)
            raw_chunk = remaining[:safe_break_idx]
            chunk = raw_chunk.rstrip()
            if chunk:
                chunks.append(chunk)
            broke_on_separator = safe_break_idx < len(remaining) and bool(
                _WS_RE.match(remaining[safe_break_idx])
            )
            next_start = min(len(remaining), safe_break_idx + (1 if broke_on_separator else 0))
            remaining = remaining[next_start:].lstrip()
        if remaining:
            chunks.append(remaining)
        return chunks


def _find_break_index(window: str) -> int:
    # Try to break at the last newline
    idx = window.rfind("\n")
    if idx > len(window) * 0.5:
        return idx
    # Or space
    idx = window.rfind(" ")
    if idx > 0:
        return idx
    return len(window)


def create_overlapping_chunks(
    text: str, max_chars: int = 1600, overlap_chars: int = 320
) -> List[str]:
    """Chunks text into approx `max_chars` chunks with `overlap_chars` overlap."""
    if not text:
        return []

    chunks = []
    pos = 0
    while pos < len(text):
        end = pos + max_chars
        if end >= len(text):
            chunks.append(text[pos:])
            break

        # Find a clean break
        window = text[pos:end]
        break_idx = _find_break_index(window)
        if break_idx <= 0:
            break_idx = len(window)

        chunks.append(text[pos : pos + break_idx].strip())

        # Advance pos, but overlap backwards
        next_pos = pos + break_idx
        pos = next_pos - overlap_chars
        if pos < next_pos - break_idx:
            # Don't loop infinitely if overlap is huge
            pos = next_pos

    return chunks


def index_memory_files(workspace_dir: str, runtime) -> int:
    """Read MEMORY.md, USER.md, memory/*.md and index them as chunks in the db."""
    workspace = Path(workspace_dir)
    target_files = []

    # 1. Identify files
    mem_md = workspace / "MEMORY.md"
    user_md = workspace / "USER.md"

    if mem_md.is_file():
        target_files.append(mem_md)
    if user_md.is_file():
        target_files.append(user_md)

    mem_dir = workspace / "memory"
    if mem_dir.is_dir():
        for f in mem_dir.glob("*.md"):
            if f.is_file():
                target_files.append(f)

    # Also support QMD extraPaths if jarvis config has them
    # For now we just index the primary ones.

    total_chunks = 0
    for file_path in target_files:
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue

        # Filename relative to workspace
        rel_name = file_path.relative_to(workspace).as_posix()

        # Clear existing chunks for this file
        runtime.delete_file_chunks(rel_name)

        # Create chunks
        chunks = create_overlapping_chunks(content)

        for i, chunk in enumerate(chunks):
            chunk_key = f"{rel_name}:{i}"
            # The .set() method extracts <!-- importance: X --> etc automatically
            file_origin = "owner" if rel_name in ("MEMORY.md", "USER.md") else "agent"
            runtime.set(
                key=chunk_key,
                value=chunk,
                category="file",
                origin=file_origin,
                project=None,
            )
        total_chunks += len(chunks)

    return total_chunks
