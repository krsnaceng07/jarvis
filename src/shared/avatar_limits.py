"""jarvis.shared.avatar_limits — browser-safe avatar payload limits.

OpenClaw parity: mirrors ``openclaw-main/src/shared/avatar-limits.ts``.
"""
from __future__ import annotations

import re

#: Maximum avatar payload size accepted by local file and Gateway upload paths.
AVATAR_MAX_BYTES = 2 * 1024 * 1024

#: SVG has the longest MIME prefix among supported local avatar formats.
_MAX_AVATAR_DATA_URL_PREFIX_LENGTH = len("data:image/svg+xml;base64,")

#: Maximum encoded length of a supported local avatar at ``AVATAR_MAX_BYTES``.
AVATAR_MAX_DATA_URL_CHARS = (
    (AVATAR_MAX_BYTES // 3 + (1 if AVATAR_MAX_BYTES % 3 else 0)) * 4
    + _MAX_AVATAR_DATA_URL_PREFIX_LENGTH
)

_AVATAR_IMAGE_DATA_URL_RE = re.compile(r"^data:image/", re.IGNORECASE)


def is_renderable_avatar_image_data_url(value: str) -> bool:
    """Accept image data URLs that fit the Gateway and Control UI payload boundary.

    Mirrors :func:`isRenderableAvatarImageDataUrl`
    (``shared/avatar-limits.ts``).
    """
    return (
        isinstance(value, str)
        and len(value) <= AVATAR_MAX_DATA_URL_CHARS
        and bool(_AVATAR_IMAGE_DATA_URL_RE.match(value))
    )


__all__ = [
    "AVATAR_MAX_BYTES",
    "AVATAR_MAX_DATA_URL_CHARS",
    "is_renderable_avatar_image_data_url",
]
