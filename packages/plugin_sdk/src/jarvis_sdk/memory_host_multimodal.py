"""jarvis_sdk.memory_host_multimodal — multimodal memory settings + file classification.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/multimodal.ts`` (117 LOC).
Multimodal memory settings normalization + file classification
(image / audio extensions).

Key port decisions:
- ``as const`` object literal → ``TypedDict`` with ``Literal`` keys.
- Default max file bytes preserved (``10 * 1024 * 1024 = 10 MB``).
- Glob builder preserves the OpenClaw case-insensitive character
  class pattern: ``*.jpg`` → ``*.[jJ][pP][gG]``.
- All function bodies preserved verbatim.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict, cast

# Re-export the ``normalize_lowercase_string_or_empty`` helper from
# the SDK. The TS source uses ``@openclaw/normalization-core/string-coerce``;
# the JARVIS SDK provides the same helper under a snake_case name.
try:
    from jarvis_normalization_core.string_coerce import (
        normalize_lowercase_string_or_empty,  # type: ignore[attr-defined]
    )
except ImportError:  # pyright: ignore[reportMissingImports]

    def normalize_lowercase_string_or_empty(value: Any) -> str:  # type: ignore[no-redef]
        if not isinstance(value, str):
            return ""
        return value.strip().lower()


# ── Modality specs (mirrors OpenClaw's ``as const``) ─────────────────


#: Memory multimodal spec per modality. Mirrors
#: OpenClaw's ``MEMORY_MULTIMODAL_SPECS``.
MEMORY_MULTIMODAL_SPECS: dict[str, dict[str, Any]] = {
    "image": {
        "labelPrefix": "Image file",
        "extensions": [
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif",
            ".heic",
            ".heif",
        ],
    },
    "audio": {
        "labelPrefix": "Audio file",
        "extensions": [
            ".mp3",
            ".wav",
            ".ogg",
            ".opus",
            ".m4a",
            ".m2a",
            ".aac",
            ".flac",
        ],
    },
}


#: Supported multimodal memory modality. Mirrors OpenClaw's
#: ``MemoryMultimodalModality``.
MemoryMultimodalModality = Literal["image", "audio"]


#: All supported multimodal memory modalities in stable config
#: order. Mirrors OpenClaw's ``MEMORY_MULTIMODAL_MODALITIES``.
MEMORY_MULTIMODAL_MODALITIES: list[str] = list(MEMORY_MULTIMODAL_SPECS.keys())


#: User selection for one modality or all modalities.
#: Mirrors OpenClaw's ``MemoryMultimodalSelection``.
MemoryMultimodalSelection = Literal["image", "audio", "all"]


class MemoryMultimodalSettings(TypedDict):
    """Normalized multimodal memory ingestion settings.

    Mirrors OpenClaw's ``MemoryMultimodalSettings``.
    """

    enabled: bool
    modalities: list[str]
    maxFileBytes: int


#: Default max bytes for one multimodal memory file.
#: Mirrors OpenClaw's ``DEFAULT_MEMORY_MULTIMODAL_MAX_FILE_BYTES``.
DEFAULT_MEMORY_MULTIMODAL_MAX_FILE_BYTES = 10 * 1024 * 1024


# ── Helpers ─────────────────────────────────────────────────────────


def _normalize_memory_multimodal_modalities(
    raw: list[MemoryMultimodalSelection] | None,
) -> list[str]:
    """Normalize user modality selections to supported modalities.

    Mirrors OpenClaw's ``normalizeMemoryMultimodalModalities``.
    ``None`` or inclusion of ``"all"`` returns the full set.
    Duplicates are de-duplicated; unsupported values are dropped.
    Preserves the input insertion order (matches the OpenClaw
    ``Set`` iteration order in JS).
    """
    if raw is None or "all" in raw:
        return list(MEMORY_MULTIMODAL_MODALITIES)
    seen: set[str] = set()
    normalized: list[str] = []
    for value in raw:
        if value in ("image", "audio") and value not in seen:
            seen.add(value)
            normalized.append(value)
    return normalized


# ── Public API ──────────────────────────────────────────────────────


def normalize_memory_multimodal_settings(
    raw: object,
) -> MemoryMultimodalSettings:
    """Normalize user multimodal settings.

    Mirrors OpenClaw's ``normalizeMemoryMultimodalSettings``. When
    ``enabled`` is not ``True``, ``modalities`` is forced to ``[]``.
    ``maxFileBytes`` is floored to ``>= 1``; defaults to 10 MB.
    ``None`` is treated as an empty settings dict.
    """
    safe_raw = cast(dict[str, object], raw if isinstance(raw, dict) else {})
    enabled = safe_raw.get("enabled") is True
    max_file_bytes_raw = safe_raw.get("maxFileBytes")
    if (
        isinstance(max_file_bytes_raw, (int, float)) and max_file_bytes_raw == max_file_bytes_raw
    ):  # NaN check
        max_file_bytes = max(1, int(max_file_bytes_raw))
    else:
        max_file_bytes = DEFAULT_MEMORY_MULTIMODAL_MAX_FILE_BYTES
    modalities_raw = safe_raw.get("modalities")
    modalities = (
        cast(
            list[MemoryMultimodalSelection] | None,
            modalities_raw if isinstance(modalities_raw, list) else None,
        )
        if enabled
        else None
    )
    return {
        "enabled": enabled,
        "modalities": (_normalize_memory_multimodal_modalities(modalities) if enabled else []),
        "maxFileBytes": max_file_bytes,
    }


def is_memory_multimodal_enabled(settings: MemoryMultimodalSettings) -> bool:
    """Return ``True`` when multimodal ingestion has at least one modality.

    Mirrors OpenClaw's ``isMemoryMultimodalEnabled``.
    """
    return bool(settings.get("enabled")) and len(settings.get("modalities", [])) > 0


def get_memory_multimodal_extensions(modality: str) -> tuple[str, ...]:
    """Return the accepted file extensions for ``modality``.

    Mirrors OpenClaw's ``getMemoryMultimodalExtensions``. Returns an
    empty tuple for an unknown modality.
    """
    spec = MEMORY_MULTIMODAL_SPECS.get(modality)
    if spec is None:
        return ()
    return tuple(spec["extensions"])


def build_memory_multimodal_label(modality: str, normalized_path: str) -> str:
    """Build the text label accompanying embedded multimodal content.

    Mirrors OpenClaw's ``buildMemoryMultimodalLabel``.
    """
    spec = MEMORY_MULTIMODAL_SPECS.get(modality)
    if spec is None:
        # Fallback: generic label. Matches the TS source's
        # behavior for an unknown modality (TypeScript would
        # return ``undefined``; we return a sane default).
        return f"File: {normalized_path}"
    return f"{spec['labelPrefix']}: {normalized_path}"


def build_case_insensitive_extension_glob(extension: str) -> str:
    """Build a glob that matches an extension case-insensitively.

    Mirrors OpenClaw's ``buildCaseInsensitiveExtensionGlob``.
    Each char in the extension becomes a character class
    ``[xX]``; the leading ``.`` is stripped first. Returns
    ``"*"`` when the extension is empty.
    """
    normalized = normalize_lowercase_string_or_empty(extension).lstrip(".")
    if not normalized:
        return "*"
    parts = [f"[{c.lower()}{c.upper()}]" for c in normalized]
    return f"*.{''.join(parts)}"


def classify_memory_multimodal_path(
    file_path: str, settings: MemoryMultimodalSettings
) -> str | None:
    """Classify ``file_path`` into a supported modality under current settings.

    Mirrors OpenClaw's ``classifyMemoryMultimodalPath``. Returns
    ``None`` when multimodal is disabled or the path doesn't match
    any enabled modality's accepted extensions.
    """
    if not is_memory_multimodal_enabled(settings):
        return None
    lower = normalize_lowercase_string_or_empty(file_path)
    if not lower:
        return None
    for modality in settings.get("modalities", []):
        for ext in get_memory_multimodal_extensions(modality):
            if lower.endswith(ext):
                return modality
    return None


__all__ = [
    "MEMORY_MULTIMODAL_SPECS",
    "MEMORY_MULTIMODAL_MODALITIES",
    "DEFAULT_MEMORY_MULTIMODAL_MAX_FILE_BYTES",
    "MemoryMultimodalModality",
    "MemoryMultimodalSelection",
    "MemoryMultimodalSettings",
    "normalize_memory_multimodal_settings",
    "is_memory_multimodal_enabled",
    "get_memory_multimodal_extensions",
    "build_memory_multimodal_label",
    "build_case_insensitive_extension_glob",
    "classify_memory_multimodal_path",
]
