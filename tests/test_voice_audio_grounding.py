"""Volume commands must match the spoken operation and number."""

import pytest

from src.talk.speech_guard import SpeechGroundingGuard


@pytest.mark.parametrize(
    "speech,args,allowed",
    [
        ("what is the volume", {"action": "get_volume"}, True),
        ("आवाज कति छ", {"action": "get_volume"}, True),
        ("set volume to 40", {"action": "set_volume", "percent": 40}, True),
        ("भोल्युम ४० गर", {"action": "set_volume", "percent": 40}, True),
        ("set volume to 40", {"action": "set_volume", "percent": 90}, False),
        ("increase volume by 10", {"action": "adjust_volume", "delta": 10}, True),
        ("आवाज १० घटाऊ", {"action": "adjust_volume", "delta": -10}, True),
        ("decrease volume by 10", {"action": "adjust_volume", "delta": 10}, False),
        ("volume up", {"action": "adjust_volume", "delta": 80}, False),
        ("unmute audio", {"action": "mute"}, False),
        ("mute audio", {"action": "mute"}, True),
        ("don't mute audio", {"action": "mute"}, False),
        ("आवाज म्युट नगर", {"action": "mute"}, False),
        ("open notepad", {"action": "mute"}, False),
    ],
)
def test_audio_grounding(speech, args, allowed):
    result = SpeechGroundingGuard().validate_voice_tool_call("audio", args, speech)
    assert result.is_allowed is allowed
