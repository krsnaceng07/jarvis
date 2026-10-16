import pytest
from unittest.mock import MagicMock

from extensions.honcho.plugin import HonchoPlugin

@pytest.fixture
def mock_api():
    api = MagicMock()
    api.config.get.return_value = {
        "apiKey": "test-key",
        "workspaceId": "test-workspace",
        "baseUrl": "http://localhost:8000"
    }
    
    # Track registered hooks
    api.hooks = {}
    def _register_hook(name, handler, priority=0):
        api.hooks[name] = handler
    api.register_hook.side_effect = _register_hook
    
    return api

@pytest.mark.asyncio
async def test_honcho_plugin_init_and_hooks(mock_api):
    plugin = HonchoPlugin()
    plugin.init(mock_api)
    
    assert "before_prompt_build" in mock_api.hooks
    assert "after_turn" in mock_api.hooks
    
    assert plugin._client is not None
    assert plugin._client.api_key == "test-key"
    assert plugin._client.workspace_id == "test-workspace"
    
    # Test before_prompt_build hook modifies prompt
    event = {"prompt": []}
    await mock_api.hooks["before_prompt_build"](event)
    assert len(event["prompt"]) == 1
    assert event["prompt"][0]["role"] == "system"
    assert "Honcho Context:" in event["prompt"][0]["content"]

@pytest.mark.asyncio
async def test_honcho_tools(mock_api):
    plugin = HonchoPlugin()
    plugin.init(mock_api)
    
    # Test context tool
    res = await plugin.call("honcho_context", {})
    assert res.is_ok
    assert "Mock Honcho Context" in res.value
    
    # Test search conclusions tool
    res = await plugin.call("honcho_search_conclusions", {"query": "test query"})
    assert res.is_ok
    assert "Mock conclusion for test query" in res.value
    
    # Test ask tool
    res = await plugin.call("honcho_ask", {"question": "who am I?", "depth": "quick"})
    assert res.is_ok
    assert "Mock answer to who am I? at depth quick" in res.value

@pytest.mark.asyncio
async def test_honcho_missing_tool(mock_api):
    plugin = HonchoPlugin()
    plugin.init(mock_api)
    
    res = await plugin.call("honcho_missing", {})
    assert res.is_err
    assert "Unknown tool" in res.error
