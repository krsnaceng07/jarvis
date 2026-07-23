"""jarvis_sdk.memory_host_multimodal_facade — public multimodal facade.

OpenClaw parity: mirrors the multimodal facade re-export in
``packages/memory-host-sdk/src/multimodal.ts`` (6 LOC). Re-exports
the multimodal settings + classification helpers.
"""
from __future__ import annotations

from .memory_host_multimodal import (
    DEFAULT_MEMORY_MULTIMODAL_MAX_FILE_BYTES,
    MEMORY_MULTIMODAL_MODALITIES,
    MEMORY_MULTIMODAL_SPECS,
    MemoryMultimodalModality,
    MemoryMultimodalSelection,
    MemoryMultimodalSettings,
    build_case_insensitive_extension_glob,
    build_memory_multimodal_label,
    classify_memory_multimodal_path,
    get_memory_multimodal_extensions,
    is_memory_multimodal_enabled,
    normalize_memory_multimodal_settings,
)

__all__ = [
    "DEFAULT_MEMORY_MULTIMODAL_MAX_FILE_BYTES",
    "MEMORY_MULTIMODAL_MODALITIES",
    "MEMORY_MULTIMODAL_SPECS",
    "MemoryMultimodalModality",
    "MemoryMultimodalSelection",
    "MemoryMultimodalSettings",
    "build_case_insensitive_extension_glob",
    "build_memory_multimodal_label",
    "classify_memory_multimodal_path",
    "get_memory_multimodal_extensions",
    "is_memory_multimodal_enabled",
    "normalize_memory_multimodal_settings",
]
