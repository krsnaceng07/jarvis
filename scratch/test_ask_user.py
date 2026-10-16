import pytest
import asyncio
import json
from src.agents.sessions.tools.ask_user import create_ask_user_tool, _ASK_USER_QUESTIONS

@pytest.fixture(autouse=True)
def cleanup():
    _ASK_USER_QUESTIONS.clear()

class MockSignal:
    def __init__(self):
        self.aborted = False
        self._callbacks = []

    def addEventListener(self, event, cb):
        if event == "abort":
            self._callbacks.append(cb)

    def removeEventListener(self, event, cb):
        if event == "abort" and cb in self._callbacks:
            self._callbacks.remove(cb)

    def abort(self):
        self.aborted = True
        for cb in self._callbacks:
            cb()

@pytest.mark.asyncio
async def test_ask_user_success():
    calls = []
    
    async def mock_gateway_call(method, opts, params, extras=None):
        calls.append((method, params))
        if method == "question.request":
            return {"id": params["id"]}
        elif method == "question.waitAnswer":
            return {"status": "answered", "answers": {"deploy_target": ["Staging"]}}
        return {}

    tool = create_ask_user_tool({
        "gateway_call": mock_gateway_call,
        "session_key": "test_session",
    })

    params = {
        "questions": [{
            "id": "deploy_target",
            "header": "Deploy",
            "question": "Where to deploy?",
            "options": [{"label": "Staging"}, {"label": "Prod"}],
            "multiSelect": False
        }],
        "timeoutSeconds": 100
    }

    result = await tool["execute"]("call_123", params, MockSignal(), None)
    
    assert "content" in result
    ans = json.loads(result["content"][0]["text"])
    assert ans["status"] == "answered"
    assert ans["answers"]["deploy_target"] == ["Staging"]
    
    # Assert calls
    assert calls[0][0] == "question.request"
    assert calls[0][1]["id"] == "call_123"
    assert calls[0][1]["sessionKey"] == "test_session"
    assert calls[1][0] == "question.waitAnswer"
    
    # Assert cleanup
    assert "call_123" not in _ASK_USER_QUESTIONS

@pytest.mark.asyncio
async def test_ask_user_timeout():
    calls = []
    
    async def mock_gateway_call(method, opts, params, extras=None):
        calls.append((method, params))
        if method == "question.request":
            return {"id": params["id"]}
        elif method == "question.waitAnswer":
            return {"status": "expired"}
        elif method == "question.resolve":
            return {}
        return {}

    tool = create_ask_user_tool({
        "gateway_call": mock_gateway_call,
        "session_key": "test_session",
    })

    params = {
        "questions": [{"id": "q", "header": "H", "question": "Q", "options": [{"label": "A"}]}],
        "timeoutSeconds": 30
    }

    result = await tool["execute"]("call_123", params, MockSignal(), None)
    
    assert "content" in result
    ans = json.loads(result["content"][0]["text"])
    assert ans["status"] == "no_answer"
    
    # Cleanup should still happen
    assert "call_123" not in _ASK_USER_QUESTIONS

@pytest.mark.asyncio
async def test_ask_user_duplicate_pending():
    async def mock_gateway_call(method, opts, params, extras=None):
        if method == "question.waitAnswer":
            await asyncio.sleep(0.5)
            return {"status": "answered"}
        return {}

    tool = create_ask_user_tool({
        "gateway_call": mock_gateway_call,
        "session_key": "test_session",
    })

    params = {
        "questions": [{"id": "q", "header": "H", "question": "Q", "options": [{"label": "A"}]}],
    }

    task1 = asyncio.create_task(tool["execute"]("call_1", params, MockSignal(), None))
    await asyncio.sleep(0.1) # Let it register
    
    # Second call should fail
    with pytest.raises(ValueError, match="already has a pending question for this session"):
        await tool["execute"]("call_2", params, MockSignal(), None)
        
    await task1
