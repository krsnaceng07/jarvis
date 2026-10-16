"""jarvis.shared.avatar_policy — avatar path + MIME helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/avatar-policy.ts``.

Public surface:

- :func:`resolve_avatar_mime`
- :func:`is_avatar_data_url`
- :func:`is_avatar_http_url`
- :func:`has_avatar_uri_scheme`
- :func:`is_windows_absolute_path`
- :func:`is_path_within_root`
- :func:`looks_like_avatar_path`
- :func:`is_supported_local_avatar_extension`
- :data:`AVATAR_MAX_BYTES`
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict


#: Maximum bytes for an inline avatar.
AVATAR_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB


#: Local inline-serving safe extensions.
_LOCAL_AVATAR_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"})

#: MIME map keyed by file extension.
_AVATAR_MIME_BY_EXT: Dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

#: Detects data URLs.
_AVATAR_DATA_RE = re.compile(r"^data:", re.IGNORECASE)

#: Detects remote HTTP(S) avatar URLs.
_AVATAR_HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)

#: Detects URI-scheme-like avatar values.
_AVATAR_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)

#: Detects Windows absolute paths so they are not mistaken for URI schemes.
_WINDOWS_ABS_RE = re.compile(r"^[a-zA-Z]:[\\/]")

#: Image-extension matcher for heuristic avatar-path detection.
_AVATAR_PATH_EXT_RE = re.compile(r"\.(png|jpe?g|gif|webp|svg|ico)$", re.IGNORECASE)


def _normalize_lower(value: Any) -> str:
    if isinstance(value, str):
        return value.strip().lower()
    return ""


def resolve_avatar_mime(file_path: str) -> str:
    """Resolve the local MIME for an avatar file by extension.

    Mirrors :func:`resolveAvatarMime` (``shared/avatar-policy.ts``).
    """
    _, ext = os.path.splitext(file_path or "")
    return _AVATAR_MIME_BY_EXT.get(_normalize_lower(ext), "application/octet-stream")


def is_avatar_data_url(value: str) -> bool:
    """Return whether ``value`` is an avatar data URL.

    Mirrors :func:`isAvatarDataUrl` (``shared/avatar-policy.ts``).
    """
    if not isinstance(value, str):
        return False
    return bool(_AVATAR_DATA_RE.match(value))


def is_avatar_http_url(value: str) -> bool:
    """Return whether ``value`` is a remote HTTP(S) avatar URL.

    Mirrors :func:`isAvatarHttpUrl` (``shared/avatar-policy.ts``).
    """
    if not isinstance(value, str):
        return False
    return bool(_AVATAR_HTTP_RE.match(value))


def has_avatar_uri_scheme(value: str) -> bool:
    """Return whether ``value`` has any URI scheme prefix.

    Mirrors :func:`hasAvatarUriScheme` (``shared/avatar-policy.ts``).
    """
    if not isinstance(value, str):
        return False
    return bool(_AVATAR_SCHEME_RE.match(value))


def is_windows_absolute_path(value: str) -> bool:
    """Return whether ``value`` is a Windows absolute path.

    Mirrors :func:`isWindowsAbsolutePath` (``shared/avatar-policy.ts``).
    """
    if not isinstance(value, str):
        return False
    return bool(_WINDOWS_ABS_RE.match(value))


def is_path_within_root(root_dir: str, target_path: str) -> bool:
    """Return whether ``target_path`` is inside ``root_dir``."""
    if not root_dir or not target_path:
        return False
    try:
        root = os.path.realpath(root_dir)
        target = os.path.realpath(target_path)
        return os.path.commonpath([root]) == os.path.commonpath([root, target])
    except (OSError, ValueError):
        return False


def looks_like_avatar_path(value: str) -> bool:
    """Heuristically detect strings that look like local avatar file paths.

    Mirrors :func:`looksLikeAvatarPath` (``shared/avatar-policy.ts``).
    """
    if not isinstance(value, str):
        return False
    if "/" in value or "\\" in value:
        return True
    return bool(_AVATAR_PATH_EXT_RE.search(value))


def is_supported_local_avatar_extension(file_path: str) -> bool:
    """Return whether ``file_path`` has a browser-safe avatar extension.

    Mirrors :func:`isSupportedLocalAvatarExtension` (``shared/avatar-policy.ts``).
    """
    _, ext = os.path.splitext(file_path or "")
    return _normalize_lower(ext) in _LOCAL_AVATAR_EXTENSIONS


__all__ = [
    "AVATAR_MAX_BYTES",
    "resolve_avatar_mime",
    "is_avatar_data_url",
    "is_avatar_http_url",
    "has_avatar_uri_scheme",
    "is_windows_absolute_path",
    "is_path_within_root",
    "looks_like_avatar_path",
    "is_supported_local_avatar_extension",
]
