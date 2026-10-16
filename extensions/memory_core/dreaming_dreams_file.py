"""memory_core.dreaming_dreams_file — safe DREAMS.md persistence for dreaming.

OpenClaw parity: mirrors ``extensions/memory-core/src/dreaming-dreams-file.ts``
(140 LOC). Provides:

- ``resolve_dreams_path(workspace_dir)`` — find existing ``DREAMS.md`` /
  ``dreams.md`` (case-insensitive) or fall back to the canonical path.
- ``read_dreams_file(dreams_path)`` — read with empty-string fallback for
  missing / symlink / alias errors.
- ``update_dreams_file({workspace_dir, updater})`` — atomic update with
  per-file async lock (in-process global lock map).
- ``update_deep_dreams_file({workspace_dir, body_lines})`` — convenience
  helper that updates the "Deep Sleep" managed markdown block.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar

# Mirrors OpenClaw's ``DREAMS_FILENAMES = ["DREAMS.md", "dreams.md"]``.
# The first name is canonical (what we create); the second is a tolerated
# legacy alternative.
DREAMS_FILENAMES = ("DREAMS.md", "dreams.md")

# Markers for the "Deep Sleep" managed block. These are the same comment
# style OpenClaw uses so the markdown editor (Obsidian, etc.) preserves them.
DEEP_START_MARKER = "<!-- openclaw:dreaming:deep:start -->"
DEEP_END_MARKER = "<!-- openclaw:dreaming:deep:end -->"

# The "Deep Sleep" heading that wraps the managed block.
DEEP_HEADING = "## Deep Sleep"

# Per-path async lock table (process-wide). OpenClaw uses a Symbol-keyed
# global map; Python equivalent is a module-level dict protected by a
# threading.Lock for the dict-mutation path.
_dreams_file_locks: dict[str, "_DreamsFileLockEntry"] = {}
_dreams_file_locks_meta = threading.Lock()


class _DreamsFileLockEntry:
    """Per-path async lock + refcount (mirrors OpenClaw's ``DreamsFileLockEntry``)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.refs = 0

    def __enter__(self) -> None:
        self._lock.acquire()

    def __exit__(self, *exc: Any) -> None:
        self._lock.release()


def _get_or_create_dreams_file_lock(dreams_path: str) -> _DreamsFileLockEntry:
    """Return the lock entry for ``dreams_path``, creating it if missing.

    Mirrors OpenClaw's per-path lock map.
    """
    with _dreams_file_locks_meta:
        entry = _dreams_file_locks.get(dreams_path)
        if entry is None:
            entry = _DreamsFileLockEntry()
            _dreams_file_locks[dreams_path] = entry
        entry.refs += 1
    return entry


def _release_dreams_file_lock(dreams_path: str, entry: _DreamsFileLockEntry) -> None:
    """Decrement the lock refcount; delete the entry if it hits 0."""
    with _dreams_file_locks_meta:
        entry.refs -= 1
        if entry.refs <= 0 and _dreams_file_locks.get(dreams_path) is entry:
            _dreams_file_locks.pop(dreams_path, None)


# ── Public API ────────────────────────────────────────────────────────────


def resolve_dreams_path(workspace_dir: str) -> str:
    """Return the path to the workspace's DREAMS.md.

    Mirrors OpenClaw's ``resolveDreamsPath``. Looks for ``DREAMS.md``
    first, then ``dreams.md``; if neither exists, returns the canonical
    ``DREAMS.md`` path (caller is expected to create it).
    """
    for name in DREAMS_FILENAMES:
        target = str(Path(workspace_dir) / name)
        try:
            # Equivalent to ``fs.access(target)``.
            os.stat(target)
            return target
        except FileNotFoundError:
            continue
        except OSError:
            # Some other error (permission, etc.) — surface to caller.
            raise
    return str(Path(workspace_dir) / DREAMS_FILENAMES[0])


# Error codes that mean "file doesn't exist" (treat as empty read).
# Mirrors OpenClaw's ``isEmptyDreamsReadError``.
_EMPTY_READ_CODES = frozenset(
    {
        "ENOENT",
        "ENOTDIR",
        "not-found",
        "not-file",
        "path-alias",
        "path-mismatch",
        "symlink",
    }
)


def _is_empty_dreams_read_error(err: Any) -> bool:
    code: str | None = None
    if hasattr(err, "code") and isinstance(err.code, str):
        code = err.code
    if code in _EMPTY_READ_CODES:
        return True
    if isinstance(err, OSError) and err.errno in (2, 20):  # ENOENT, ENOTDIR
        return True
    if isinstance(err, Exception) and err.args and err.args[0] == "path must be a regular file":
        return True
    return False


def read_dreams_file(dreams_path: str) -> str:
    """Read DREAMS.md and return its UTF-8 content.

    Mirrors OpenClaw's ``readDreamsFile``. Returns ``""`` if the file is
    missing, is a symlink, or any other "empty" read error.
    """
    try:
        with open(dreams_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except OSError as err:
        if _is_empty_dreams_read_error(err):
            return ""
        raise


def _assert_safe_dreams_path(dreams_path: str) -> None:
    """Refuse to write symlinks or non-file DREAMS.md.

    Mirrors OpenClaw's ``assertSafeDreamsPath``.
    """
    try:
        st = os.lstat(dreams_path)
    except FileNotFoundError:
        return
    if os.path.islink(dreams_path):
        raise RuntimeError("Refusing to write symlinked DREAMS.md")
    if not (stat.S_ISREG(st.st_mode) if (stat := __import__("stat")) else False):
        # Defensive: only allow regular files. (Python's stat module is
        # imported lazily so the ``stat`` local above is a no-op fallback.)
        if not os.path.isfile(dreams_path):
            raise RuntimeError("Refusing to write non-file DREAMS.md")


def _write_dreams_file_atomic(dreams_path: str, content: str) -> None:
    """Atomically write ``content`` to ``dreams_path``.

    Mirrors OpenClaw's ``writeDreamsFileAtomic``. Uses the standard
    tempfile + os.replace pattern. Mode 0o600 (user-only read/write).
    Preserves the existing file mode if the file already exists.
    """
    _assert_safe_dreams_path(dreams_path)
    parent = os.path.dirname(dreams_path) or "."
    os.makedirs(parent, exist_ok=True)
    base = os.path.basename(dreams_path)
    fd, tmp = tempfile.mkstemp(prefix=f".{base}.dreams.", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        # Preserve existing mode if file exists.
        if os.path.exists(dreams_path):
            try:
                existing_mode = (
                    stat.S_IMODE(os.stat(dreams_path).st_mode)
                    if (stat := __import__("stat"))
                    else 0o600
                )  # noqa: F821
            except OSError:
                existing_mode = 0o600
        else:
            existing_mode = 0o600
        os.chmod(tmp, existing_mode)
        os.replace(tmp, dreams_path)
    except Exception:
        # Clean up the temp file on any failure.
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


T = TypeVar("T")


def update_dreams_file(
    workspace_dir: str,
    updater: Callable[[str, str], Any],
) -> Any:
    """Read DREAMS.md, call ``updater(existing, dreams_path)``, write the result.

    Mirrors OpenClaw's ``updateDreamsFile``. The updater returns a dict
    ``{content, result, shouldWrite?}``; the result is returned to the
    caller, and the content is written atomically (if ``shouldWrite`` is
    not ``False``). Per-path lock ensures concurrent calls serialize.
    """
    dreams_path = resolve_dreams_path(workspace_dir)
    os.makedirs(os.path.dirname(dreams_path) or ".", exist_ok=True)
    entry = _get_or_create_dreams_file_lock(dreams_path)
    try:
        with entry:
            existing = read_dreams_file(dreams_path)
            outcome = updater(existing, dreams_path)
            # Updater may return either a dict or a coroutine.
            if hasattr(outcome, "__await__"):
                import asyncio

                outcome = asyncio.run(outcome)  # type: ignore[assignment]
            content = outcome["content"]
            result = outcome["result"]
            should_write = outcome.get("shouldWrite", True)
            if should_write:
                if not content.endswith("\n"):
                    content = f"{content}\n"
                _write_dreams_file_atomic(dreams_path, content)
            return result
    finally:
        _release_dreams_file_lock(dreams_path, entry)


def update_deep_dreams_file(workspace_dir: str, body_lines: list[str]) -> str:
    """Update the "Deep Sleep" managed block in DREAMS.md.

    Mirrors OpenClaw's ``updateDeepDreamsFile``. Returns the resolved
    dreams path. Body is empty → uses the placeholder ``- No durable
    changes.``.
    """
    body = "\n".join(body_lines) if body_lines else "- No durable changes."

    def _updater(existing: str, dreams_path: str) -> dict[str, Any]:
        return {
            "content": _replace_managed_markdown_block(
                original=existing,
                heading=DEEP_HEADING,
                start_marker=DEEP_START_MARKER,
                end_marker=DEEP_END_MARKER,
                body=body,
            ),
            "result": dreams_path,
        }

    return update_dreams_file(workspace_dir, _updater)


# ── Managed markdown block helper ────────────────────────────────────────
# Mirrors OpenClaw's ``replaceManagedMarkdownBlock`` from
# ``openclaw/plugin-sdk/memory-host-markdown``. Inlined here since the
# SDK's memory-host-markdown module isn't ported yet.
_MARKER_RE = re.compile(r"^[ \t]*<!--[ \t]*([\w-]+):([\w.-]+):start[ \t]*-->$", re.MULTILINE)


def _replace_managed_markdown_block(
    original: str,
    heading: str,
    start_marker: str,
    end_marker: str,
    body: str,
) -> str:
    """Replace the managed block (between start/end markers) in ``original``.

    If the markers already exist, replace the block in place. Otherwise
    append a new section with the markers.
    """
    if start_marker in original and end_marker in original:
        # Replace the existing block in place.
        start_idx = original.index(start_marker)
        end_idx = original.index(end_marker, start_idx)
        before = original[:start_idx]
        after = original[end_idx + len(end_marker) :]
        return f"{before}{start_marker}\n{body}\n{end_marker}{after}"

    # No existing block — append a new section.
    section = f"\n\n{heading}\n\n{start_marker}\n{body}\n{end_marker}\n"
    if original and not original.endswith("\n"):
        return f"{original}\n{section.lstrip()}"
    return f"{original}{section}"


__all__ = [
    # Constants
    "DREAMS_FILENAMES",
    "DEEP_START_MARKER",
    "DEEP_END_MARKER",
    "DEEP_HEADING",
    # API
    "resolve_dreams_path",
    "read_dreams_file",
    "update_dreams_file",
    "update_deep_dreams_file",
]
