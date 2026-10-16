"""File Transfer file system operations."""

from __future__ import annotations

import base64
import io
import mimetypes
import os
from pathlib import Path
import tempfile
from typing import Any
import zipfile

from .policy import MAX_FILE_BYTES, normalize_path_for_policy


def is_binary_bytes(data: bytes) -> bool:
    """Check if byte sequence is binary (contains null bytes or invalid UTF-8)."""
    if b"\x00" in data[:4096]:
        return True
    try:
        data.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def fetch_file(path_str: str, max_bytes: int = MAX_FILE_BYTES) -> dict[str, Any]:
    """Read a local file up to max_bytes."""
    p = Path(normalize_path_for_policy(path_str))
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"File not found: {path_str}")

    size = p.stat().st_size
    if size > max_bytes:
        raise ValueError(f"File size ({size} bytes) exceeds maximum limit ({max_bytes} bytes)")

    with open(p, "rb") as f:
        raw_bytes = f.read(max_bytes)

    is_bin = is_binary_bytes(raw_bytes)
    mime_type, _ = mimetypes.guess_type(str(p))
    mime = mime_type or ("application/octet-stream" if is_bin else "text/plain")

    if is_bin:
        content_str = base64.b64encode(raw_bytes).decode("ascii")
    else:
        content_str = raw_bytes.decode("utf-8", errors="replace")

    return {
        "path": str(p),
        "bytes": len(raw_bytes),
        "content": content_str,
        "isText": not is_bin,
        "mimeType": mime,
    }


def write_file(
    path_str: str,
    content: str | bytes,
    is_base64: bool = False,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Write content to a file atomically."""
    p = Path(normalize_path_for_policy(path_str))
    if p.exists() and not overwrite:
        raise FileExistsError(f"File already exists: {path_str}")

    if isinstance(content, str):
        if is_base64:
            payload = base64.b64decode(content)
        else:
            payload = content.encode("utf-8")
    else:
        payload = content

    p.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write via tempfile in same dir
    temp_fd, temp_path = tempfile.mkstemp(dir=p.parent, prefix=".tmp_transfer_")
    try:
        with os.fdopen(temp_fd, "wb") as f:
            f.write(payload)
        os.replace(temp_path, p)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    return {
        "path": str(p),
        "bytesWritten": len(payload),
    }


def list_dir(
    path_str: str,
    recursive: bool = False,
    max_depth: int = 5,
) -> dict[str, Any]:
    """List contents of a directory."""
    root_path = Path(normalize_path_for_policy(path_str))
    if not root_path.exists() or not root_path.is_dir():
        raise NotADirectoryError(f"Directory not found: {path_str}")

    entries: list[dict[str, Any]] = []

    def _scan(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            for item in current.iterdir():
                is_dir = item.is_dir()
                stat = item.stat()
                entries.append(
                    {
                        "name": item.name,
                        "path": str(item),
                        "isDirectory": is_dir,
                        "isFile": item.is_file(),
                        "isSymlink": item.is_symlink(),
                        "size": stat.st_size if not is_dir else 0,
                        "modifiedTime": int(stat.st_mtime * 1000),
                    }
                )
                if is_dir and recursive:
                    _scan(item, depth + 1)
        except PermissionError:
            pass

    _scan(root_path, 0)
    return {
        "path": str(root_path),
        "entries": entries,
        "count": len(entries),
    }


def fetch_dir(path_str: str, archive_format: str = "zip") -> bytes:
    """Create an archive buffer from a directory."""
    root_path = Path(normalize_path_for_policy(path_str))
    if not root_path.exists() or not root_path.is_dir():
        raise NotADirectoryError(f"Directory not found: {path_str}")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(root_path):
            for file in files:
                file_p = Path(root) / file
                arcname = file_p.relative_to(root_path)
                zipf.write(file_p, arcname)

    return buffer.getvalue()
