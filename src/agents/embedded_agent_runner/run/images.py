"""jarvis.agents.embedded_agent_runner.run.images — detect/resolve/load prompt image references.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/images.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`IMAGE_EXTENSION_NAMES` — tuple of supported image file
  extensions.
- :data:`IMAGE_EXTENSIONS` — set of supported image extensions
  (with leading ``.``).
- :data:`MEDIA_URI_REGEX` — precompiled regex matching
  ``media://inbound/<id>`` URIs.
- :data:`DetectedImageRef` — TypedDict for a detected image
  reference.
- :func:`is_image_extension` — return True if the path has a
  supported image extension.
- :func:`detect_image_references` — detect image references in
  text (paths + media URIs).
- :func:`resolve_image_reference` — resolve a detected
  reference to a local path (delegated to an installable hook).
- :func:`load_image` — load an image from a resolved reference
  (delegated to an installable hook).
- :func:`merge_prompt_attachment_images` — merge inline,
  offloaded, and prompt-ref images into a final image list.

Phase 7.6a — focused minimal port.

The OpenClaw source is 580+ lines and tightly coupled to the
media-reference resolver, sandbox-media-paths, web-media loader,
and image-sanitization layers. The Python port keeps the public
surface and delegates the heavy resolution + loading to
installable hooks so the host can plug in the real layers as
they land.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple


#: Image file extensions. Mirrors
#: :data:`IMAGE_EXTENSION_NAMES`` (``images.ts:25-36``).
IMAGE_EXTENSION_NAMES: Tuple[str, ...] = (
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "bmp",
    "tiff",
    "tif",
    "heic",
    "heif",
)


#: Image extensions with leading dot. Mirrors
#: :data:`IMAGE_EXTENSIONS`` (``images.ts:37-40``).
IMAGE_EXTENSIONS: Set[str] = {f".{ext}" for ext in IMAGE_EXTENSION_NAMES}


#: Media-URI regex matching ``media://inbound/<id>`` URIs. Mirrors
#: :data:`MEDIA_URI_REGEX`` (``images.ts:81``).
MEDIA_URI_REGEX: "re.Pattern[str]" = re.compile(
    r"\bmedia://inbound/([^\]\s/\\]+)"
)


#: Detected image reference shape. Mirrors
#: :class:`DetectedImageRef`` (``images.ts:86-93``).
DetectedImageRef = Dict[str, Any]


#: Async resolve-image-reference hook. The host installs the
#: real :func:`resolveMediaReferenceLocalPath`` when the
#: media-reference layer lands. The default returns the
#: resolved string unchanged.
_RESOLVE_IMAGE_REFERENCE: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]] = (
    lambda params: _default_resolve(params)
)


async def _default_resolve(params: Dict[str, Any]) -> Dict[str, Any]:
    return dict(params)


def set_resolve_image_reference_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
) -> None:
    """Install a custom resolve-image-reference hook."""
    global _RESOLVE_IMAGE_REFERENCE
    _RESOLVE_IMAGE_REFERENCE = hook


#: Async load-image hook.
_LOAD_IMAGE: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]] = (
    lambda params: _default_resolve(params)
)


def set_load_image_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
) -> None:
    """Install a custom load-image hook."""
    global _LOAD_IMAGE
    _LOAD_IMAGE = hook


def is_image_extension(file_path: str) -> bool:
    """Return True if ``file_path`` has a supported image extension.

    Mirrors :func:`isImageExtension`` (``images.ts:98-101``).
    """
    if not isinstance(file_path, str):
        return False
    _, ext = os.path.splitext(file_path)
    return ext.lower() in IMAGE_EXTENSIONS


def _normalize_ref_for_dedupe(raw: str) -> str:
    """Normalize ``raw`` for dedup keying.

    Mirrors :func:`normalizeRefForDedupe`` (``images.ts:103-105``).
    """
    if sys.platform == "win32":
        return raw.lower()
    return raw


def _is_openclaw_cli_image_cache_path(file_path: str) -> bool:
    """Return True if ``file_path`` is under the CLI image cache.

    Mirrors :func:`isOpenClawCliImageCachePath`` (``images.ts:107-116``).
    """
    parts = file_path.replace("\\", "/").split("/")
    for index, part in enumerate(parts):
        if part == ".openclaw-cli-images":
            return True
        if part == "openclaw-cli-images" and index > 0:
            parent = parts[index - 1]
            if re.match(r"^openclaw(?:-\d+)?$", parent):
                return True
    return False


def detect_image_references(prompt: str) -> List[DetectedImageRef]:
    """Detect image references (paths + media URIs) in ``prompt``.

    Mirrors the regex-based detection in
    :func:`detectImageReferencesInPrompt`` (``images.ts:...``).
    """
    if not isinstance(prompt, str) or not prompt:
        return []
    refs: List[DetectedImageRef] = []
    seen: Set[str] = set()
    for match in MEDIA_URI_REGEX.finditer(prompt):
        ref_id = match.group(1)
        key = f"media-uri\0{ref_id}"
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            {
                "raw": match.group(0),
                "type": "media-uri",
                "resolved": match.group(0),
                "id": ref_id,
            }
        )
    path_regexes: List["re.Pattern[str]"] = [
        re.compile(
            r"^\s*(.+?\.(?:" + "|".join(IMAGE_EXTENSION_NAMES) + r"))\s*(?:\(|$|\|)",
            re.IGNORECASE,
        ),
        re.compile(
            r"\[Image:\s*source:\s*([^\]]+\.(?:" + "|".join(IMAGE_EXTENSION_NAMES) + r"))\]",
            re.IGNORECASE,
        ),
        re.compile(
            r"file://([^\s<>\"'`\]]+\.(?:" + "|".join(IMAGE_EXTENSION_NAMES) + r"))",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:^|\s|[\"'`(])([A-Za-z]:[\\/][^\s\"'`()\[\]]*\.(?:"
            + "|".join(IMAGE_EXTENSION_NAMES)
            + r"))",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:^|\s|[\"'`(])((\.\.?/|[~/])[^\s\"'`()\[\]]*\.(?:"
            + "|".join(IMAGE_EXTENSION_NAMES)
            + r"))",
            re.IGNORECASE,
        ),
    ]
    for regex in path_regexes:
        for match in regex.finditer(prompt):
            path = match.group(1).strip()
            if not path:
                continue
            # Media URIs (media://inbound/<id>) are detected and added
            # by the MEDIA_URI_REGEX pass above. The non-greedy path
            # regex can swallow a media URI as a "path" when the URI is
            # the entire prompt — guard that case so we don't emit a
            # second ref with the wrong type.
            if path.startswith("media://"):
                continue
            key = f"path\0{_normalize_ref_for_dedupe(path)}"
            if key in seen:
                continue
            seen.add(key)
            refs.append(
                {
                    "raw": match.group(0),
                    "type": "path",
                    "resolved": path,
                }
            )
    return refs


async def resolve_image_reference(
    ref: DetectedImageRef,
) -> Optional[Dict[str, Any]]:
    """Resolve a detected image reference to a local path.

    Mirrors :func:`resolveImageReferenceLocalPath`` (``images.ts:...``).
    The Python port delegates to an installable hook.
    """
    result = await _RESOLVE_IMAGE_REFERENCE(dict(ref))
    if not result:
        return None
    return result


async def load_image(
    resolved: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Load an image from a resolved reference.

    Mirrors the image loading flow in the OpenClaw source. The
    Python port delegates to an installable hook.
    """
    result = await _LOAD_IMAGE(dict(resolved))
    if not result:
        return None
    return result


def merge_prompt_attachment_images(
    *,
    image_order: Optional[List[Any]] = None,
    existing_images: Optional[List[Dict[str, Any]]] = None,
    offloaded_images: Optional[List[Optional[Dict[str, Any]]]] = None,
    prompt_ref_images: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Merge inline, offloaded, and prompt-ref images into a final list.

    Mirrors :func:`mergePromptAttachmentImages`` (``images.ts:123-167``).
    """
    prompt_images: List[Dict[str, Any]] = []
    existing = list(existing_images or [])
    offloaded = list(offloaded_images or [])
    if image_order and len(image_order) > 0:
        inline_index = 0
        offloaded_index = 0
        for entry in image_order:
            if entry == "inline":
                image = existing[inline_index] if inline_index < len(existing) else None
                if image is not None:
                    prompt_images.append(image)
                inline_index += 1
                continue
            image = (
                offloaded[offloaded_index]
                if offloaded_index < len(offloaded)
                else None
            )
            if image is not None:
                prompt_images.append(image)
            offloaded_index += 1
        for image in existing[inline_index:]:
            prompt_images.append(image)
        for image in offloaded[offloaded_index:]:
            if image is not None:
                prompt_images.append(image)
    else:
        prompt_images.extend(existing)
        for image in offloaded:
            if image is not None:
                prompt_images.append(image)
    if prompt_ref_images:
        prompt_images.extend(prompt_ref_images)
    return prompt_images


__all__ = [
    "DetectedImageRef",
    "IMAGE_EXTENSIONS",
    "IMAGE_EXTENSION_NAMES",
    "MEDIA_URI_REGEX",
    "detect_image_references",
    "is_image_extension",
    "load_image",
    "merge_prompt_attachment_images",
    "resolve_image_reference",
    "set_load_image_hook",
    "set_resolve_image_reference_hook",
]
