import asyncio
import logging
import sys
import os

paths = [
    "packages/agent_runtime/src",
    "packages/plugin_sdk/src",
    "packages/llm_client/src",
    "packages/memory_host_sdk/src",
    "packages/config_core/src",
    "packages/normalization_core/src",
    "packages/mcp_core/src",
    "packages/state_core/src",
    "packages/events_core/src",
    "src",
    ""
]
for p in reversed(paths):
    sys.path.insert(0, os.path.join('E:\\jarvis', p))

# Configure logging to go to stdout
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

from src.agents.sessions.sdk import create_agent_session, CreateAgentSessionOptions
from src.agents.sessions.model_registry import ModelRegistry
from src.agents.sessions.session_manager import SessionManager
from jarvis_config_core import load_config, McpConfig, McpServerConfig
import jarvis_config_core

class MockSettingsManager:
    def get_steering_mode(self): return "all"
    def get_follow_up_mode(self): return "all"

class MockSessionManager(SessionManager):
    def get_session_id(self): return "test_session_id"
    def _create_tools(self, *args, **kwargs): return []

class MockModelRegistry(ModelRegistry):
    pass

async def main():
    options = CreateAgentSessionOptions(
        cwd="E:\\jarvis",
        session_manager=MockSessionManager(),
        settings_manager=MockSettingsManager(),
        model_registry=MockModelRegistry(),
        model={"provider": "google", "id": "gemini-2.0-flash"}
    )
    
    cfg = load_config()
    if cfg.mcp is None:
        cfg.mcp = McpConfig(servers={})
        
    cfg.mcp.servers["test_everything"] = McpServerConfig(
        command="npx.cmd",
        args=["-y", "@modelcontextprotocol/server-everything"],
        enabled=True
    )
    
    jarvis_config_core.load_config = lambda *args, **kwargs: cfg
        
    try:
        print("Creating agent session...")
        result = await create_agent_session(options)
        session = result["session"]
        
        tools = session.get_active_tool_names()
        print(f"Total tools injected: {len(tools)}")
        print(f"Tool names: {tools}")
        
        mcp_tools = [t for t in tools if t.startswith("mcp_test_everything_")]
        print(f"MCP tools: {mcp_tools}")
        if len(mcp_tools) == 0:
            print("ERROR: No MCP tools were injected")
    except Exception as e:
        print(f"Exception occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
