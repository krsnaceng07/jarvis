import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "mcp_core", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "config_core", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "plugin_sdk", "src")))

from src.agents.sessions.sdk import create_agent_session, CreateAgentSessionOptions
from jarvis_config_core import load_config

import logging
logging.basicConfig(level=logging.DEBUG)

class MockSettingsManager:
    def get_steering_mode(self): return "all"
    def get_follow_up_mode(self): return "all"
    def get_transport(self): return "auto"
    def get_thinking_budgets(self): return None
    def get_provider_retry_settings(self): return {}
    def get_agent_defaults(self): return {}

class MockSessionManager:
    def get_session_id(self): return "test-session"
    def get_messages(self): return []
    def save_messages(self, messages): pass
class MockModelRegistry:
    def get_model(self, *args, **kwargs): return {"provider": "google", "id": "gemini-2.0-flash"}

import shutil

@pytest.mark.live
@pytest.mark.asyncio
async def test_mcp_tools_injected():
    if not os.environ.get("UV_LIVE_TEST") and not os.environ.get("JARVIS_LIVE_TEST"):
        pytest.skip("Live MCP test skipped unless UV_LIVE_TEST=1")
    if not shutil.which("npx"):
        pytest.skip("npx not available in environment")
    cwd = os.getcwd()
    model_registry = MockModelRegistry() # type: ignore
    session_manager = MockSessionManager()
    settings_manager = MockSettingsManager()
    
    options = CreateAgentSessionOptions(
        cwd=cwd,
        model_registry=model_registry,
        session_manager=session_manager,
        settings_manager=settings_manager,
        model={"provider": "google", "id": "gemini-2.0-flash"}
    )
    
    cfg = load_config()
    if cfg.mcp is None:
        from jarvis_config_core import McpConfig
        cfg.mcp = McpConfig(servers={})
        
    from jarvis_config_core import McpServerConfig
    cfg.mcp.servers["test_everything"] = McpServerConfig(
        command="npx.cmd",
        args=["-y", "@modelcontextprotocol/server-everything"],
        enabled=True
    )
    
    # Mock load_config for create_agent_session
    import jarvis_config_core
    jarvis_config_core.load_config = lambda *args, **kwargs: cfg
        
    try:
        result = await create_agent_session(options)
        session = result["session"]
        
        tools = session.get_active_tool_names()
        print(f"Total tools injected: {len(tools)}")
        print(f"Tool names: {tools}")
        
        mcp_tools = [t for t in tools if t.startswith("mcp_test_everything_")]
        
        try:
            assert len(mcp_tools) > 0, "MCP tools were not injected"
        except AssertionError:
            with open("test_fail_log.txt", "w") as f:
                f.write(f"Assertion failed: mcp_tools={mcp_tools}, all tools={tools}\n")
            import sys
            sys.exit(1)
        assert "mcp_test_everything_echo" in mcp_tools, "Expected test_everything_echo tool"
        
        # Test executing the echo tool
        echo_tool = session.tool_registry["mcp_test_everything_echo"]
        # In test_everything, echo takes a "message" parameter
        result = await echo_tool["execute"]("call_123", {"message": "hello jarvis"})
        
        print(f"Echo tool result: {result}")
        assert result is not None
        assert "hello jarvis" in result.content[0].text
        
    except Exception:
        import traceback
        with open("test_fail_log.txt", "w") as f:
            f.write(traceback.format_exc())
        import sys
        sys.exit(1)

