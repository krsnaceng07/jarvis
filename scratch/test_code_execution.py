import pytest
from unittest.mock import patch, MagicMock
from extensions.xai.code_execution import execute_code_execution, build_missing_api_key_payload

@pytest.mark.asyncio
async def test_code_execution_missing_api_key():
    result = await execute_code_execution(task="print(1+1)", api_key=None)
    assert result == build_missing_api_key_payload()
    assert result["error"] == "missing_xai_api_key"

@pytest.mark.asyncio
@patch("extensions.xai.code_execution.httpx.AsyncClient.post")
async def test_code_execution_success(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "text": "The result is 2",
        "citations": ["doc1", "doc2"],
        "output": [{"type": "code_interpreter_call"}]
    }
    mock_post.return_value = mock_response
    
    result = await execute_code_execution(task="print(1+1)", api_key="sk-test", config={"model": "grok-4.3"})
    
    assert "content" in result
    assert result["content"][0]["text"] == "The result is 2"
    assert "details" in result
    assert result["details"]["citations"] == ["doc1", "doc2"]
    assert result["details"]["usedCodeExecution"] is True
    assert "code_interpreter_call" in result["details"]["outputTypes"]

@pytest.mark.asyncio
@patch("extensions.xai.code_execution.httpx.AsyncClient.post")
async def test_code_execution_api_error(mock_post):
    from httpx import HTTPError
    mock_post.side_effect = HTTPError("Internal Server Error")
    
    result = await execute_code_execution(task="print(1+1)", api_key="sk-test", config={"model": "grok-4.3"})
    
    assert result["error"] == "xai_api_error"
    assert "xAI code execution failed" in result["message"]
