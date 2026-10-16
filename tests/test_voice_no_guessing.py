"""Unresolved speech cannot authorize model-selected actions."""

import pytest

from src.talk.speech_guard import SpeechGroundingGuard


@pytest.mark.parametrize(
    "speech", ["", "hmm", "i was thinking", "राम्रोसँग सुन", "maybe we should check"]
)
@pytest.mark.parametrize(
    "tool,args",
    [
        ("browser", {"action": "open", "url": "https://example.com"}),
        ("desktop", {"action": "send", "recipient": "someone", "message": "hello"}),
        ("exec", {"command": "echo unsolicited"}),
    ],
)
def test_unresolved_speech_never_authorizes_a_tool(speech, tool, args):
    guard = SpeechGroundingGuard()
    assert not guard.validate_voice_tool_call(tool, args, speech).is_allowed
    assert guard.confirmation_scope.pending is None


def test_local_app_command_cannot_be_diverted_to_a_website():
    result = SpeechGroundingGuard().validate_voice_tool_call(
        "browser", {"action": "open", "url": "https://example.com"}, "open notepad"
    )
    assert result.repaired_tool_name == "open_path"
    assert result.repaired_args == {"target": "notepad"}


@pytest.mark.parametrize(
    "speech,allowed",
    [
        ("telegram bata reply aayena", True),
        ("टेलिग्रामबाट जवाफ आएन", True),
        ("check whatsapp channel", True),
        ("open notepad", False),
        ("hmm", False),
    ],
)
def test_channel_diagnostic_grounding(speech, allowed):
    result = SpeechGroundingGuard().validate_voice_tool_call("channel_status", {}, speech)
    assert result.is_allowed is allowed


@pytest.mark.parametrize(
    "speech",
    [
        "open browser",
        "browser open gara",
        "chrome khola",
    ],
)
def test_explicit_browser_open_is_grounded(speech):
    result = SpeechGroundingGuard().validate_voice_tool_call(
        "browser", {"action": "open", "url": "about:blank"}, speech
    )
    assert result.is_allowed is True


def test_browser_word_alone_does_not_authorize_random_navigation():
    result = SpeechGroundingGuard().validate_voice_tool_call(
        "browser", {"action": "open", "url": "https://example.com"}, "browser"
    )
    assert result.is_allowed is False


@pytest.mark.parametrize(
    "tool,args,speech",
    [
        ("memory_search", {"query": "telegram reply"}, "memory ma telegram reply search gara"),
        ("memory_search", {"query": "channel bug"}, "yaad bata channel bug khoja"),
        ("configure_channel", {"channel": "telegram", "token": "redacted"}, "telegram channel configure gara"),
        ("configure_channel", {"channel": "whatsapp"}, "whatsapp bot connect gar"),
        ("open_path", {"target": "notepad.py"}, "open notepad.py"),
        ("open_path", {"target": "terminal"}, "terminal khola"),
    ],
)
def test_explicit_voice_commands_authorize_matching_tools(tool, args, speech):
    result = SpeechGroundingGuard().validate_voice_tool_call(tool, args, speech)
    assert result.is_allowed is True


@pytest.mark.parametrize(
    "tool,args",
    [
        ("memory_search", {"query": "telegram reply"}),
        ("configure_channel", {"channel": "telegram", "token": "redacted"}),
        ("open_path", {"target": "notepad.py"}),
    ],
)
def test_unclear_speech_still_blocks_sensitive_or_stateful_tools(tool, args):
    result = SpeechGroundingGuard().validate_voice_tool_call(tool, args, "maybe we should check")
    assert result.is_allowed is False
