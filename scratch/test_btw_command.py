from src.auto_reply.reply.btw_command import is_btw_request_text, extract_btw_question

def test_is_btw_request_text():
    assert is_btw_request_text("/btw") is True
    assert is_btw_request_text("/side") is True
    assert is_btw_request_text("/btw what changed?") is True
    assert is_btw_request_text("/side what changed?") is True
    assert is_btw_request_text("/btw:") is True
    assert is_btw_request_text("/side:") is True
    
    # Should not match
    assert is_btw_request_text("/btwwhat") is False
    assert is_btw_request_text(" /btw") is True
    assert is_btw_request_text("hello /btw") is False
    assert is_btw_request_text("") is False
    assert is_btw_request_text(None) is False

def test_extract_btw_question():
    assert extract_btw_question("/btw") == ""
    assert extract_btw_question("/side") == ""
    assert extract_btw_question("/btw what changed?") == "what changed?"
    assert extract_btw_question("/side what changed?") == "what changed?"
    assert extract_btw_question("/btw \nwhat changed?") == "what changed?"
    
    assert extract_btw_question("/something else") is None
    assert extract_btw_question("") is None
    assert extract_btw_question(None) is None

import pytest
from src.auto_reply.reply.commands_btw import handle_btw_command

class MockParams:
    def __init__(self, command_body: str, session_key="session-123"):
        self.command = {"commandBodyNormalized": command_body}
        self.sessionKey = session_key
        self.sessionStore = {session_key: {"sessionId": "sess-123", "transcript": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]}}
        self.sessionEntry = self.sessionStore[session_key]
        self.cfg = {}
        self.agentDir = "/tmp"
        self.provider = "test"
        self.model = "test-model"

@pytest.mark.asyncio
async def test_handle_btw_command():
    # Test valid btw
    params = MockParams("/btw what is this?")
    result = await handle_btw_command(params, allow_text_commands=True)
    assert result is not None
    assert result["shouldContinue"] is False
    assert "reply" in result
    assert "This is a side-question response for: what is this?" in result["reply"]["text"]
    assert result["reply"]["btw"]["question"] == "what is this?"

    # Test not allowed
    assert await handle_btw_command(params, allow_text_commands=False) is None

    # Test missing btw
    params_no_btw = MockParams("hello")
    assert await handle_btw_command(params_no_btw, allow_text_commands=True) is None

    # Test empty question
    params_empty = MockParams("/btw")
    result_empty = await handle_btw_command(params_empty, allow_text_commands=True)
    assert result_empty is not None
    assert result_empty["shouldContinue"] is False
    assert "Usage: /btw" in result_empty["reply"]["text"]

