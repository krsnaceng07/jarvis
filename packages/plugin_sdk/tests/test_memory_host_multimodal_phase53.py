"""Tests for jarvis_sdk.memory_host_multimodal (Phase 5.3a).

Mirrors the TypeScript test patterns from
``packages/memory-host-sdk/src/host/multimodal.test.ts``.
"""

from __future__ import annotations


from typing import cast

from jarvis_sdk.memory_host_multimodal import (
    DEFAULT_MEMORY_MULTIMODAL_MAX_FILE_BYTES,
    MEMORY_MULTIMODAL_MODALITIES,
    MEMORY_MULTIMODAL_SPECS,
    MemoryMultimodalSettings,
    build_case_insensitive_extension_glob,
    build_memory_multimodal_label,
    classify_memory_multimodal_path,
    get_memory_multimodal_extensions,
    is_memory_multimodal_enabled,
    normalize_memory_multimodal_settings,
)


# ── Constants ────────────────────────────────────────────────────────


def test_default_max_file_bytes() -> None:
    """Default cap is 10 MB."""
    assert DEFAULT_MEMORY_MULTIMODAL_MAX_FILE_BYTES == 10 * 1024 * 1024


def test_modalities_list_order() -> None:
    """Modalities are listed in stable order (image, audio)."""
    assert MEMORY_MULTIMODAL_MODALITIES == ["image", "audio"]


def test_modality_specs_contain_image_and_audio() -> None:
    """Specs include the two supported modalities."""
    assert "image" in MEMORY_MULTIMODAL_SPECS
    assert "audio" in MEMORY_MULTIMODAL_SPECS


def test_image_extensions() -> None:
    """Image extensions cover the documented formats."""
    exts = get_memory_multimodal_extensions("image")
    for expected in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"):
        assert expected in exts


def test_audio_extensions() -> None:
    """Audio extensions cover the documented formats."""
    exts = get_memory_multimodal_extensions("audio")
    for expected in (".mp3", ".wav", ".ogg", ".opus", ".m4a", ".m2a", ".aac", ".flac"):
        assert expected in exts


def test_get_extensions_unknown_modality() -> None:
    """Unknown modality returns an empty tuple."""
    assert get_memory_multimodal_extensions("video") == ()


# ── normalize_memory_multimodal_settings ────────────────────────────


def test_normalize_disabled() -> None:
    """Disabled settings → empty modalities list."""
    s = normalize_memory_multimodal_settings({"enabled": False})
    assert s["enabled"] is False
    assert s["modalities"] == []
    assert s["maxFileBytes"] == DEFAULT_MEMORY_MULTIMODAL_MAX_FILE_BYTES


def test_normalize_enabled_default_modalities() -> None:
    """Enabled without explicit modalities → all modalities."""
    s = normalize_memory_multimodal_settings({"enabled": True})
    assert s["enabled"] is True
    assert s["modalities"] == ["image", "audio"]


def test_normalize_enabled_explicit_modalities() -> None:
    """Enabled with explicit modalities → kept (sorted, de-duped)."""
    s = normalize_memory_multimodal_settings({"enabled": True, "modalities": ["audio"]})
    assert s["modalities"] == ["audio"]


def test_normalize_enabled_with_all_modality() -> None:
    """``"all"`` modality returns the full set."""
    s = normalize_memory_multimodal_settings({"enabled": True, "modalities": ["all"]})
    assert s["modalities"] == ["image", "audio"]


def test_normalize_enabled_with_unsupported_modalities() -> None:
    """Unsupported modalities are dropped."""
    s = normalize_memory_multimodal_settings(
        {"enabled": True, "modalities": ["image", "video", "audio"]}
    )
    # Sorted: image, audio (video dropped)
    assert s["modalities"] == ["image", "audio"]


def test_normalize_max_file_bytes_default() -> None:
    """Missing ``maxFileBytes`` → default."""
    s = normalize_memory_multimodal_settings({"enabled": True})
    assert s["maxFileBytes"] == DEFAULT_MEMORY_MULTIMODAL_MAX_FILE_BYTES


def test_normalize_max_file_bytes_explicit() -> None:
    """Explicit ``maxFileBytes`` is floored to ``>= 1``."""
    s = normalize_memory_multimodal_settings({"enabled": True, "maxFileBytes": 5_000_000})
    assert s["maxFileBytes"] == 5_000_000


def test_normalize_max_file_bytes_negative_floored() -> None:
    """Negative ``maxFileBytes`` is floored to 1."""
    s = normalize_memory_multimodal_settings({"enabled": True, "maxFileBytes": -100})
    assert s["maxFileBytes"] == 1


def test_normalize_max_file_bytes_zero_floored() -> None:
    """Zero ``maxFileBytes`` is floored to 1."""
    s = normalize_memory_multimodal_settings({"enabled": True, "maxFileBytes": 0})
    assert s["maxFileBytes"] == 1


def test_normalize_max_file_bytes_float_truncated() -> None:
    """Float ``maxFileBytes`` is truncated to int."""
    s = normalize_memory_multimodal_settings({"enabled": True, "maxFileBytes": 5_000_000.7})
    assert s["maxFileBytes"] == 5_000_000


# ── is_memory_multimodal_enabled ─────────────────────────────────────


def test_is_enabled_true() -> None:
    """Enabled with modalities → True."""
    s = normalize_memory_multimodal_settings({"enabled": True})
    assert is_memory_multimodal_enabled(s) is True


def test_is_enabled_false_when_disabled() -> None:
    """Disabled → False."""
    s = normalize_memory_multimodal_settings({"enabled": False})
    assert is_memory_multimodal_enabled(s) is False


def test_is_enabled_false_when_no_modalities() -> None:
    """Enabled but no modalities → False."""
    s = cast(
        MemoryMultimodalSettings,
        {
            "enabled": True,
            "modalities": [],
            "maxFileBytes": 100,
        },
    )
    assert is_memory_multimodal_enabled(s) is False


# ── build_memory_multimodal_label ──────────────────────────────────


def test_label_image() -> None:
    """Image label format: ``"Image file: <path>"``."""
    label = build_memory_multimodal_label("image", "memory/photo.png")
    assert label == "Image file: memory/photo.png"


def test_label_audio() -> None:
    """Audio label format: ``"Audio file: <path>"``."""
    label = build_memory_multimodal_label("audio", "memory/clip.mp3")
    assert label == "Audio file: memory/clip.mp3"


def test_label_unknown_modality_fallback() -> None:
    """Unknown modality → generic ``"File: <path>"`` fallback."""
    label = build_memory_multimodal_label("video", "memory/clip.mp4")
    assert label == "File: memory/clip.mp4"


# ── build_case_insensitive_extension_glob ─────────────────────────


def test_glob_simple() -> None:
    """``.jpg`` → ``*.[jJ][pP][gG]``."""
    assert build_case_insensitive_extension_glob(".jpg") == "*.[jJ][pP][gG]"


def test_glob_with_leading_dot_stripped() -> None:
    """``jpg`` (no dot) → ``*.[jJ][pP][gG]`` (dot is stripped)."""
    assert build_case_insensitive_extension_glob("jpg") == "*.[jJ][pP][gG]"


def test_glob_empty_returns_star() -> None:
    """Empty / whitespace-only extension → ``"*"``."""
    assert build_case_insensitive_extension_glob("") == "*"
    assert build_case_insensitive_extension_glob(".") == "*"


def test_glob_long_extension() -> None:
    """``heic`` → ``*.[hH][eE][iI][cC]``."""
    assert build_case_insensitive_extension_glob(".heic") == "*.[hH][eE][iI][cC]"


# ── classify_memory_multimodal_path ────────────────────────────────


def test_classify_png_as_image() -> None:
    """A ``.png`` path classifies as ``"image"`` when image is enabled."""
    s = normalize_memory_multimodal_settings({"enabled": True})
    assert classify_memory_multimodal_path("/foo/bar.png", s) == "image"


def test_classify_uppercase_extension() -> None:
    """``.PNG`` matches (case-insensitive)."""
    s = normalize_memory_multimodal_settings({"enabled": True})
    assert classify_memory_multimodal_path("/foo/bar.PNG", s) == "image"


def test_classify_jpeg_as_image() -> None:
    """``.jpeg`` matches image extensions."""
    s = normalize_memory_multimodal_settings({"enabled": True})
    assert classify_memory_multimodal_path("/foo/bar.jpeg", s) == "image"


def test_classify_mp3_as_audio() -> None:
    """``.mp3`` classifies as ``"audio"`` when audio is enabled."""
    s = normalize_memory_multimodal_settings({"enabled": True})
    assert classify_memory_multimodal_path("/foo/bar.mp3", s) == "audio"


def test_classify_unknown_extension_returns_none() -> None:
    """Unknown extension → ``None`` (no match)."""
    s = normalize_memory_multimodal_settings({"enabled": True})
    assert classify_memory_multimodal_path("/foo/bar.xyz", s) is None


def test_classify_when_disabled_returns_none() -> None:
    """Disabled settings → ``None`` regardless of extension."""
    s = normalize_memory_multimodal_settings({"enabled": False})
    assert classify_memory_multimodal_path("/foo/bar.png", s) is None


def test_classify_when_only_audio_enabled() -> None:
    """Image extension with only audio enabled → ``None``."""
    s = normalize_memory_multimodal_settings({"enabled": True, "modalities": ["audio"]})
    assert classify_memory_multimodal_path("/foo/bar.png", s) is None
    assert classify_memory_multimodal_path("/foo/bar.mp3", s) == "audio"


def test_classify_when_only_image_enabled() -> None:
    """Audio extension with only image enabled → ``None``."""
    s = normalize_memory_multimodal_settings({"enabled": True, "modalities": ["image"]})
    assert classify_memory_multimodal_path("/foo/bar.mp3", s) is None
    assert classify_memory_multimodal_path("/foo/bar.png", s) == "image"


def test_classify_path_with_query() -> None:
    """Path with query string — the .png extension is still matched.

    Note: The OpenClaw behavior is ``endswith`` on the full path,
    so ``/foo/bar.png?v=1`` does NOT match ``.png`` (the path
    ends with ``?v=1``). In JARVIS we follow the same behavior.
    """
    s = normalize_memory_multimodal_settings({"enabled": True})
    # The query string prevents the endswith check from matching.
    assert classify_memory_multimodal_path("/foo/bar.png?v=1", s) is None
    # But a path that ends with .png (no query string) does match.
    assert classify_memory_multimodal_path("/foo/bar.png", s) == "image"


def test_classify_returns_first_match() -> None:
    """When two modalities share an extension (none currently do),
    the first enabled modality wins."""
    s = normalize_memory_multimodal_settings({"enabled": True})
    # Iteration order: image first (in MEMORY_MULTIMODAL_MODALITIES)
    # then audio. ``.jpg`` → image.
    assert classify_memory_multimodal_path("/foo/bar.jpg", s) == "image"
