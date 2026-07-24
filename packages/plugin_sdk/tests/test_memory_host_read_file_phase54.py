"""Tests for memory_host_read_file — mirrors host/read-file.ts.

Covers path safety, transient retry, and agent config integration.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make the SDK importable when running this file in isolation.
_PKG_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PKG_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from jarvis_sdk.memory_host_read_file import (  # noqa: E402
    read_agent_memory_file,
    read_memory_file,
)


# ── read_memory_file ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_root_memory_file(tmp_path: Path) -> None:
    """The canonical ``MEMORY.md`` is readable."""
    (tmp_path / "MEMORY.md").write_text("hello world", encoding="utf-8")
    result = await read_memory_file(str(tmp_path), rel_path="MEMORY.md")
    assert result["text"] == "hello world"
    assert result["path"] == "MEMORY.md"


@pytest.mark.asyncio
async def test_read_memory_file_in_memory_dir(tmp_path: Path) -> None:
    """A markdown file under ``memory/`` is readable."""
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "note.md").write_text("note content", encoding="utf-8")
    result = await read_memory_file(str(tmp_path), rel_path="memory/note.md")
    assert result["text"] == "note content"


@pytest.mark.asyncio
async def test_read_memory_file_empty_path() -> None:
    """An empty ``rel_path`` raises ``ValueError("path required")``."""
    with pytest.raises(ValueError, match="path required"):
        await read_memory_file("/tmp", rel_path="")


@pytest.mark.asyncio
async def test_read_memory_file_whitespace_path() -> None:
    """A whitespace-only ``rel_path`` raises ``ValueError``."""
    with pytest.raises(ValueError, match="path required"):
        await read_memory_file("/tmp", rel_path="   ")


@pytest.mark.asyncio
async def test_read_memory_file_non_markdown_raises(tmp_path: Path) -> None:
    """Reading a non-markdown memory path raises ``ValueError``."""
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ValueError, match="path required"):
        await read_memory_file(str(tmp_path), rel_path="memory/image.png")


@pytest.mark.asyncio
async def test_read_memory_file_outside_workspace_raises(tmp_path: Path) -> None:
    """A path outside the workspace is rejected."""
    other = tmp_path / "other"
    other.mkdir()
    (other / "foo.md").write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError, match="path required"):
        # Use an absolute path that's clearly outside the workspace.
        await read_memory_file(
            str(tmp_path),
            rel_path=str(other / "foo.md"),
        )


@pytest.mark.asyncio
async def test_read_memory_file_missing_returns_empty(tmp_path: Path) -> None:
    """A missing file returns ``{"text": "", ...}`` (not an error)."""
    result = await read_memory_file(str(tmp_path), rel_path="memory/missing.md")
    assert result["text"] == ""
    assert result["path"] == "memory/missing.md"


@pytest.mark.asyncio
async def test_read_memory_file_extra_paths_markdown(tmp_path: Path) -> None:
    """Markdown files in extra paths are readable."""
    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "note.md").write_text("from extra", encoding="utf-8")
    result = await read_memory_file(
        str(tmp_path),
        extra_paths=[str(extra)],
        rel_path=str(extra / "note.md"),
    )
    assert result["text"] == "from extra"


@pytest.mark.asyncio
async def test_read_memory_file_extra_paths_symlink_rejected(tmp_path: Path) -> None:
    """A symlinked file in an extra path is rejected (no symlink escapes)."""
    import os as _os

    if sys.platform == "win32":
        # Symlinks require elevation on Windows; skip if not available.
        try:
            _os.symlink
        except AttributeError:
            pytest.skip("symlink not available")
    extra = tmp_path / "extra"
    extra.mkdir()
    real_target = tmp_path / "real.md"
    real_target.write_text("real content", encoding="utf-8")
    symlink = extra / "fake.md"
    try:
        _os.symlink(real_target, symlink)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform")
    with pytest.raises(ValueError, match="path required"):
        await read_memory_file(
            str(tmp_path),
            extra_paths=[str(extra)],
            rel_path=str(symlink),
        )


@pytest.mark.asyncio
async def test_read_memory_file_respects_from_and_lines(tmp_path: Path) -> None:
    """``from_`` and ``lines`` are forwarded to the slice helper.

    A continuation notice is appended when more lines follow
    the slice (matches OpenClaw's
    ``build_memory_read_result_from_slice`` behavior).
    """
    mem = tmp_path / "memory"
    mem.mkdir()
    content = "\n".join(f"line {i}" for i in range(1, 21))
    # Write with explicit ``\n`` (no universal-newline translation).
    (mem / "doc.md").write_bytes(content.encode("utf-8"))
    result = await read_memory_file(
        str(tmp_path),
        rel_path="memory/doc.md",
        from_=5,
        lines=3,
    )
    assert result["text"].startswith("line 5\nline 6\nline 7")
    assert "from=8" in result["text"]  # continuation notice
    assert result["from"] == 5
    assert result["lines"] == 3
    assert result["nextFrom"] == 8


@pytest.mark.asyncio
async def test_read_memory_file_max_chars_truncates(tmp_path: Path) -> None:
    """``max_chars`` truncates the output."""
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "long.md").write_text("x" * 1000, encoding="utf-8")
    result = await read_memory_file(
        str(tmp_path),
        rel_path="memory/long.md",
        max_chars=50,
    )
    # The fitted text portion (before the notice) is <= 50 chars.
    notice_idx = result["text"].find("\n\n")
    if notice_idx >= 0:
        fitted = result["text"][:notice_idx]
    else:
        fitted = result["text"]
    assert len(fitted) <= 50


@pytest.mark.asyncio
async def test_read_memory_file_extra_paths_missing_file_empty_text(tmp_path: Path) -> None:
    """A missing file in an extra path returns empty text (not an error).

    Mirrors the workspace behavior: ``stat_regular_file`` reports
    ``missing=True`` for non-existent files, and the reader
    returns ``{"text": "", "path": rel}`` instead of raising.
    """
    extra = tmp_path / "extra"
    extra.mkdir()
    result = await read_memory_file(
        str(tmp_path),
        extra_paths=[str(extra)],
        rel_path=str(extra / "missing.md"),
    )
    assert result["text"] == ""


# ── read_agent_memory_file ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_agent_memory_disabled_raises(tmp_path: Path) -> None:
    """``memory search disabled`` is raised when the agent has it off."""
    cfg = {
        "agents": {
            "list": [
                {
                    "id": "main",
                    "memorySearch": {"enabled": False},
                }
            ]
        }
    }
    with pytest.raises(ValueError, match="memory search disabled"):
        await read_agent_memory_file(cfg, "main", "MEMORY.md")


@pytest.mark.asyncio
async def test_read_agent_memory_default_workspace(tmp_path: Path) -> None:
    """When the agent's workspace is configured, the file is read from it."""
    workspace = tmp_path / "agent_workspace"
    workspace.mkdir()
    (workspace / "MEMORY.md").write_text("agent notes", encoding="utf-8")
    cfg = {
        "agents": {
            "list": [
                {
                    "id": "main",
                    "workspace": str(workspace),
                    "memorySearch": {"enabled": True},
                }
            ]
        }
    }
    result = await read_agent_memory_file(cfg, "main", "MEMORY.md")
    assert result["text"] == "agent notes"


@pytest.mark.asyncio
async def test_read_agent_memory_extra_paths(tmp_path: Path) -> None:
    """Extra paths from the agent's memorySearch are honored."""
    workspace = tmp_path / "agent_workspace"
    workspace.mkdir()
    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "x.md").write_text("extra content", encoding="utf-8")
    cfg = {
        "agents": {
            "list": [
                {
                    "id": "main",
                    "workspace": str(workspace),
                    "memorySearch": {
                        "enabled": True,
                        "extraPaths": [str(extra)],
                    },
                }
            ]
        }
    }
    result = await read_agent_memory_file(cfg, "main", str(extra / "x.md"))
    assert result["text"] == "extra content"


@pytest.mark.asyncio
async def test_read_agent_memory_context_limits_applied(tmp_path: Path) -> None:
    """``contextLimits.memoryGetDefaultLines`` is forwarded."""
    workspace = tmp_path / "agent_workspace"
    workspace.mkdir()
    content = "\n".join(f"L{i}" for i in range(50))
    (workspace / "MEMORY.md").write_text(content, encoding="utf-8")
    cfg = {
        "agents": {
            "list": [
                {
                    "id": "main",
                    "workspace": str(workspace),
                    "memorySearch": {"enabled": True},
                    "contextLimits": {"memoryGetDefaultLines": 5},
                }
            ]
        }
    }
    result = await read_agent_memory_file(cfg, "main", "MEMORY.md")
    # Only 5 lines returned.
    assert result["lines"] == 5
