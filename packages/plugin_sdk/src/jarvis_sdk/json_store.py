"""jarvis_sdk.json_store — JSON file helpers for plugin runtime state.

OpenClaw parity: mirrors
``openclaw/plugin-sdk/json-store``'s
``readJsonFileWithFallback`` /
``writeJsonFileAtomically`` /
``loadJsonFile`` / ``saveJsonFile`` helpers.

Used by the memory-wiki state stores
(source-sync-state + import-runs-state) for
their legacy on-disk fallback paths and by the
host runtime for token / state caches.

The Python port uses ``pathlib`` + stdlib
``json``; atomic writes go through
``os.replace`` for crash-safety, and missing /
corrupt files are handled by the ``Fallback``
helper.
"""

from __future__ import annotations

import contextlib
import json
import os
import uuid
from pathlib import Path
from typing import IO, Any, TypeVar

_T = TypeVar("_T")


def _read_text(path: Path) -> str | None:
    """Read ``path`` as UTF-8; return None on missing or unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def load_json_file(file_path: str | os.PathLike[str]) -> Any | None:
    """Read a small JSON file synchronously. Returns None on missing/invalid.

    Mirrors OpenClaw's ``loadJsonFile``. Used for
    token / state caches where a missing file
    means "no cached value".
    """
    path = Path(file_path)
    text = _read_text(path)
    if text is None:
        return None
    try:
        result: Any = json.loads(text)
    except json.JSONDecodeError:
        return None
    return result


def save_json_file(file_path: str | os.PathLike[str], value: Any) -> None:
    """Persist a small JSON blob synchronously with atomic semantics.

    Mirrors OpenClaw's ``saveJsonFile``. Writes
    to a sibling ``.tmp`` first, then renames
    via ``os.replace``.
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            f.write(json.dumps(value, ensure_ascii=False, indent=2))
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def read_json_file_with_fallback(
    file_path: str | os.PathLike[str],
    fallback: _T,
) -> dict[str, _T | bool]:
    """Read JSON from disk; fall back cleanly when missing or invalid.

    Mirrors OpenClaw's
    ``readJsonFileWithFallback``. Returns
    ``{"value": <parsed or fallback>, "exists": <bool>}``:

    - ``exists=True`` + ``value=parsed`` when the
      file is readable and parses as JSON.
    - ``exists=False`` + ``value=fallback`` when
      the file is missing.
    - ``exists=True`` + ``value=fallback`` when
      the file exists but is unparseable (so
      callers can distinguish corrupt from
      missing).

    The result is wrapped in a ``dict`` (not a
    TypedDict) so callers can import without the
    strict-shape dependency and so the same
    pattern survives Python 3.13's evolving
    TypedDict semantics.
    """
    path = Path(file_path)
    text = _read_text(path)
    if text is None:
        return {"value": fallback, "exists": False}
    try:
        parsed: _T = json.loads(text)  # type: ignore[assignment]
    except json.JSONDecodeError:
        return {"value": fallback, "exists": True}
    return {"value": parsed, "exists": True}


def write_json_file_atomically(
    file_path: str | os.PathLike[str],
    value: Any,
    *,
    _file: IO[str] | None = None,
) -> None:
    """Write JSON with atomic-replacement semantics.

    Mirrors OpenClaw's
    ``writeJsonFileAtomically``. The optional
    ``_file`` parameter is a test seam: tests
    inject a file-like object so they can
    assert the JSON write without touching the
    real filesystem.

    The default implementation creates the
    parent directory, writes the JSON to a
    sibling ``.tmp``, and renames via
    ``os.replace``.
    """
    if _file is not None:
        json.dump(value, _file, ensure_ascii=False, indent=2)
        _file.write("\n")
        return
    save_json_file(file_path, value)


__all__ = [
    "load_json_file",
    "save_json_file",
    "read_json_file_with_fallback",
    "write_json_file_atomically",
]
