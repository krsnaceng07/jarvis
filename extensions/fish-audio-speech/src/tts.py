"""Fish Audio HTTP client for buffered and streaming TTS plus voice discovery.

OpenClaw parity: mirrors extensions/fish-audio-speech/tts.ts.
"""

from __future__ import annotations

import json
from typing import Any, Literal, TypedDict
import urllib.parse
import urllib.request
import urllib.error

FISH_AUDIO_BASE_URL = "https://api.fish.audio"
FISH_AUDIO_VOICES_MAX_BYTES = 2 * 1024 * 1024
FISH_AUDIO_VOICE_PAGE_SIZE = 100
FISH_AUDIO_MAX_OWN_VOICE_PAGES = 20
FISH_AUDIO_STREAM_MAX_BYTES = 50 * 1024 * 1024

FishAudioModel = Literal["s2.1-pro-free", "s2.1-pro", "s2-pro", "s1"]
FishAudioLatency = Literal["low", "balanced", "normal"]
FishAudioFormat = Literal["mp3", "opus", "wav", "pcm"]


class SpeechVoiceOption(TypedDict, total=False):
    id: str
    name: str | None
    description: str | None
    category: str | None
    locale: str | None
    personalities: list[str] | None


class FishAudioTtsRequest(TypedDict, total=False):
    text: str
    apiKey: str
    baseUrl: str
    model: FishAudioModel
    referenceId: str | None
    format: FishAudioFormat
    sampleRate: int | None
    latency: FishAudioLatency | None
    speed: float | None
    temperature: float | None
    topP: float | None
    normalize: bool | None
    timeoutMs: int
    maxBytes: int


def normalize_fish_audio_base_url(value: str | None = None) -> str:
    if value and value.strip():
        return value.strip().rstrip("/")
    return FISH_AUDIO_BASE_URL


def build_fish_audio_request_body(params: dict[str, Any]) -> str:
    body: dict[str, Any] = {
        "text": params.get("text", ""),
        "format": params.get("format", "mp3"),
    }
    if params.get("referenceId"):
        body["reference_id"] = params["referenceId"]
    if params.get("sampleRate") is not None:
        body["sample_rate"] = params["sampleRate"]
    if params.get("latency") is not None:
        body["latency"] = params["latency"]
    if params.get("speed") is not None:
        body["prosody"] = {"speed": params["speed"]}
    if params.get("temperature") is not None:
        body["temperature"] = params["temperature"]
    if params.get("topP") is not None:
        body["top_p"] = params["topP"]
    if params.get("normalize") is not None:
        body["normalize"] = params["normalize"]
    return json.dumps(body)


def parse_voice_item(value: Any) -> SpeechVoiceOption | None:
    if not isinstance(value, dict):
        return None
    raw_id = value.get("_id")
    if not raw_id or not isinstance(raw_id, str) or not raw_id.strip():
        return None
    voice_id = raw_id.strip()
    languages = (
        [x.strip() for x in value.get("languages", []) if isinstance(x, str) and x.strip()]
        if isinstance(value.get("languages"), list)
        else []
    )
    tags = (
        [x.strip() for x in value.get("tags", []) if isinstance(x, str) and x.strip()]
        if isinstance(value.get("tags"), list)
        else []
    )
    return {
        "id": voice_id,
        "name": str(value.get("title")).strip() if value.get("title") else None,
        "description": str(value.get("description")).strip() if value.get("description") else None,
        "category": str(value.get("visibility")).strip() if value.get("visibility") else None,
        "locale": languages[0] if languages else None,
        "personalities": tags if tags else None,
    }


async def fish_audio_tts(params: dict[str, Any]) -> bytes:
    """Perform synchronous TTS request and return bytes."""
    base_url = normalize_fish_audio_base_url(params.get("baseUrl"))
    url = f"{base_url}/v1/tts"
    headers = {
        "Authorization": f"Bearer {params.get('apiKey', '')}",
        "Content-Type": "application/json",
        "model": str(params.get("model", "s2.1-pro")),
    }
    body_data = build_fish_audio_request_body(params).encode("utf-8")
    timeout_s = max(1.0, float(params.get("timeoutMs", 240000)) / 1000.0)

    req = urllib.request.Request(url, data=body_data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = resp.read()
            max_bytes = params.get("maxBytes", FISH_AUDIO_STREAM_MAX_BYTES)
            if len(data) > max_bytes:
                raise ValueError(
                    f"Fish Audio TTS API error: audio response exceeds {max_bytes} bytes"
                )
            return data
    except urllib.error.HTTPError as err:
        err_msg = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Fish Audio TTS API error ({err.code}): {err_msg}") from err
    except Exception as err:
        raise RuntimeError(f"Fish Audio TTS API error: {err}") from err


async def list_fish_audio_voices(params: dict[str, Any]) -> list[SpeechVoiceOption]:
    """Retrieve list of available voices from Fish Audio."""
    base_url = normalize_fish_audio_base_url(params.get("baseUrl"))
    api_key = params.get("apiKey", "")
    timeout_s = max(1.0, float(params.get("timeoutMs", 30000)) / 1000.0)
    headers = {"Authorization": f"Bearer {api_key}"}

    own: list[SpeechVoiceOption] = []
    for page_number in range(1, FISH_AUDIO_MAX_OWN_VOICE_PAGES + 1):
        query = urllib.parse.urlencode(
            {
                "type": "tts",
                "page_size": str(FISH_AUDIO_VOICE_PAGE_SIZE),
                "page_number": str(page_number),
                "self": "true",
            }
        )
        url = f"{base_url}/model?{query}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw_json = json.loads(resp.read().decode("utf-8"))
                items = raw_json.get("items", [])
                if isinstance(items, list):
                    for item in items:
                        parsed = parse_voice_item(item)
                        if parsed:
                            own.append(parsed)
                if len(items) < FISH_AUDIO_VOICE_PAGE_SIZE or len(own) >= raw_json.get(
                    "total", 999999
                ):
                    break
        except Exception:
            break

    public_voices: list[SpeechVoiceOption] = []
    try:
        query = urllib.parse.urlencode(
            {
                "type": "tts",
                "page_size": str(FISH_AUDIO_VOICE_PAGE_SIZE),
                "page_number": "1",
                "sort_by": "score",
            }
        )
        url = f"{base_url}/model?{query}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw_json = json.loads(resp.read().decode("utf-8"))
            items = raw_json.get("items", [])
            if isinstance(items, list):
                for item in items:
                    parsed = parse_voice_item(item)
                    if parsed:
                        public_voices.append(parsed)
    except Exception:
        pass

    seen: set[str] = set()
    result: list[SpeechVoiceOption] = []
    for v in own + public_voices:
        vid = v.get("id")
        if vid and vid not in seen:
            seen.add(vid)
            result.append(v)
    return result
