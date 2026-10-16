"""
Media registration APIs for JARVIS Plugin SDK.
"""

from jarvis_media.image_generation.provider_registry import (
    register_image_generation_provider,
    get_image_generation_provider,
    list_image_generation_providers,
)

from jarvis_media.video_generation.provider_registry import (
    register_video_generation_provider,
    get_video_generation_provider,
    list_video_generation_providers,
)

from jarvis_media.music_generation.provider_registry import (
    register_music_generation_provider,
    get_music_generation_provider,
    list_music_generation_providers,
)

from jarvis_media.tts.provider_registry import (
    register_tts_provider,
    get_tts_provider,
    list_tts_providers,
)

from jarvis_media.stt.provider_registry import (
    register_stt_provider,
    get_stt_provider,
    list_stt_providers,
)

__all__ = [
    "register_image_generation_provider",
    "get_image_generation_provider",
    "list_image_generation_providers",
    "register_video_generation_provider",
    "get_video_generation_provider",
    "list_video_generation_providers",
    "register_music_generation_provider",
    "get_music_generation_provider",
    "list_music_generation_providers",
    "register_tts_provider",
    "get_tts_provider",
    "list_tts_providers",
    "register_stt_provider",
    "get_stt_provider",
    "list_stt_providers",
]
