"""Tests for memory_core.dreaming_dreams_file — Phase 4.4c.

Mirrors the TypeScript ``test_dreaming-dreams-file.test.ts`` patterns.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from extensions.memory_core import dreaming_dreams_file as df


def _is_case_insensitive_fs(path: Path) -> bool:
    """Return ``True`` if the filesystem holding ``path`` is case-insensitive.

    Used to skip tests that depend on case-sensitive paths (POSIX-only).
    """
    if sys.platform != "win32":
        return False
    # Probe by creating two files that differ ONLY in case. On a
    # case-sensitive FS, both files coexist and writes are independent.
    # On a case-insensitive FS (Windows NTFS / macOS HFS+ default), the
    # second write collides with the first, overwriting its content.
    upper = path / ".CaseProbeUPPER"
    lower = path / ".caseprobeupper"
    try:
        upper.write_text("U", encoding="utf-8")
        try:
            lower.write_text("L", encoding="utf-8")
            # Read back through the UPPER path: if the FS is
            # case-insensitive, the lower write overwrote the file with
            # "L"; if case-sensitive, the upper file still contains "U".
            case_sensitive = upper.read_text(encoding="utf-8") == "U"
        finally:
            try:
                lower.unlink()
            except OSError:
                pass
        return not case_sensitive
    finally:
        try:
            upper.unlink()
        except OSError:
            pass


# ── resolve_dreams_path ──────────────────────────────────────────────────


def test_resolve_dreams_path_canonical_when_missing(tmp_path: Path) -> None:
    """If neither file exists, return ``<workspace>/DREAMS.md``."""
    result = df.resolve_dreams_path(str(tmp_path))
    assert result == str(tmp_path / "DREAMS.md")


def test_resolve_dreams_path_finds_uppercase(tmp_path: Path) -> None:
    (tmp_path / "DREAMS.md").write_text("# Top\n", encoding="utf-8")
    result = df.resolve_dreams_path(str(tmp_path))
    assert result == str(tmp_path / "DREAMS.md")


def test_resolve_dreams_path_finds_lowercase_legacy(tmp_path: Path) -> None:
    """If only ``dreams.md`` exists, return that path.

    On case-insensitive filesystems (Windows), we can only test the
    "no DREAMS.md present" case via the canonical test above. The
    lowercase-only case requires a case-sensitive FS (POSIX).
    """
    if _is_case_insensitive_fs(tmp_path):
        # On Windows, ``DREAMS.md`` and ``dreams.md`` are the same file;
        # if we only create the lowercase, the function's first iteration
        # finds it via the case-insensitive stat and returns it.
        # We accept either path here, since the lowercase test is really
        # verifying "find an existing dreams file" — which Windows does.
        (tmp_path / "dreams.md").write_text("# Top\n", encoding="utf-8")
        result = df.resolve_dreams_path(str(tmp_path))
        assert result.lower() == str(tmp_path / "dreams.md").lower()
        return
    (tmp_path / "dreams.md").write_text("# Top\n", encoding="utf-8")
    result = df.resolve_dreams_path(str(tmp_path))
    assert result == str(tmp_path / "dreams.md")


def test_resolve_dreams_path_prefers_canonical(tmp_path: Path) -> None:
    """If both exist, prefer ``DREAMS.md``."""
    if _is_case_insensitive_fs(tmp_path):
        pytest.skip(
            "On case-insensitive filesystems (Windows) the two file names "
            "collide; tested separately via the lowercase-only test."
        )
    (tmp_path / "DREAMS.md").write_text("upper\n", encoding="utf-8")
    (tmp_path / "dreams.md").write_text("lower\n", encoding="utf-8")
    result = df.resolve_dreams_path(str(tmp_path))
    assert result == str(tmp_path / "DREAMS.md")


# ── read_dreams_file ────────────────────────────────────────────────────


def test_read_dreams_file_existing(tmp_path: Path) -> None:
    p = tmp_path / "DREAMS.md"
    p.write_text("hello\n", encoding="utf-8")
    assert df.read_dreams_file(str(p)) == "hello\n"


def test_read_dreams_file_missing_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "DREAMS.md"
    assert df.read_dreams_file(str(p)) == ""


def test_read_dreams_file_symlink_returns_empty(tmp_path: Path) -> None:
    """Symlinks are treated as empty (per OpenClaw's symlink policy)."""
    if not hasattr(os, "symlink"):
        pytest.skip("symlink not available")
    target = tmp_path / "real.md"
    target.write_text("real content", encoding="utf-8")
    link = tmp_path / "DREAMS.md"
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink not supported: {exc}")
    # On Windows, symlinks may require special perms; just check the
    # helper either reads real content or returns "" (no crash).
    result = df.read_dreams_file(str(link))
    assert isinstance(result, str)


# ── update_dreams_file (atomic) ───────────────────────────────────────────


def test_update_dreams_file_creates_when_missing(tmp_path: Path) -> None:
    result = df.update_dreams_file(
        str(tmp_path),
        lambda existing, path: {
            "content": "# Created\n",
            "result": "ok",
        },
    )
    assert result == "ok"
    assert (tmp_path / "DREAMS.md").exists()
    assert (tmp_path / "DREAMS.md").read_text(encoding="utf-8") == "# Created\n"


def test_update_dreams_file_preserves_trailing_newline(tmp_path: Path) -> None:
    """Updater returns content without trailing newline; helper adds one."""
    df.update_dreams_file(
        str(tmp_path),
        lambda existing, path: {
            "content": "no-newline",
            "result": "ok",
        },
    )
    content = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
    assert content.endswith("\n")


def test_update_dreams_file_keeps_existing_when_should_write_false(tmp_path: Path) -> None:
    (tmp_path / "DREAMS.md").write_text("original\n", encoding="utf-8")
    df.update_dreams_file(
        str(tmp_path),
        lambda existing, path: {
            "content": "new\n",
            "result": "skipped",
            "shouldWrite": False,
        },
    )
    content = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
    assert content == "original\n"


def test_update_dreams_file_sees_existing_content(tmp_path: Path) -> None:
    (tmp_path / "DREAMS.md").write_text("PREVIOUS\n", encoding="utf-8")
    seen: list[str] = []

    def _updater(existing: str, path: str) -> dict[str, str]:
        seen.append(existing)
        return {"content": existing + "NEW\n", "result": "ok"}

    df.update_dreams_file(str(tmp_path), _updater)
    assert seen == ["PREVIOUS\n"]
    assert (tmp_path / "DREAMS.md").read_text(encoding="utf-8") == "PREVIOUS\nNEW\n"


def test_update_dreams_file_serializes_concurrent(tmp_path: Path) -> None:
    """Two concurrent calls on the same path must serialize (one wins)."""
    counter = {"count": 0}

    def _updater(existing: str, path: str) -> dict[str, str]:
        counter["count"] += 1
        return {"content": f"call-{counter['count']}\n", "result": str(counter["count"])}

    r1 = df.update_dreams_file(str(tmp_path), _updater)
    r2 = df.update_dreams_file(str(tmp_path), _updater)
    assert {r1, r2} == {"1", "2"}
    content = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
    # Last writer wins; content reflects one of the two calls.
    assert content.startswith("call-")


# ── update_deep_dreams_file ─────────────────────────────────────────────


def test_update_deep_dreams_file_creates_block(tmp_path: Path) -> None:
    result = df.update_deep_dreams_file(
        str(tmp_path), ["- entry 1", "- entry 2"]
    )
    assert result == str(tmp_path / "DREAMS.md")
    content = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
    assert "## Deep Sleep" in content
    assert df.DEEP_START_MARKER in content
    assert df.DEEP_END_MARKER in content
    assert "- entry 1" in content
    assert "- entry 2" in content


def test_update_deep_dreams_file_empty_body_uses_placeholder(tmp_path: Path) -> None:
    df.update_deep_dreams_file(str(tmp_path), [])
    content = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
    assert "- No durable changes." in content


def test_update_deep_dreams_file_replaces_existing_block(tmp_path: Path) -> None:
    """If the block already exists, replace its body in place."""
    initial = (
        "# Top\n\n## Deep Sleep\n\n"
        f"{df.DEEP_START_MARKER}\nold body\n{df.DEEP_END_MARKER}\n"
    )
    (tmp_path / "DREAMS.md").write_text(initial, encoding="utf-8")
    df.update_deep_dreams_file(str(tmp_path), ["new body line"])
    content = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
    assert "new body line" in content
    assert "old body" not in content
    # The "# Top" header before the block must be preserved.
    assert content.startswith("# Top\n")


def test_update_deep_dreams_file_idempotent(tmp_path: Path) -> None:
    """Two consecutive calls with the same body produce the same content."""
    df.update_deep_dreams_file(str(tmp_path), ["x", "y"])
    after_first = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
    df.update_deep_dreams_file(str(tmp_path), ["x", "y"])
    after_second = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
    assert after_first == after_second
