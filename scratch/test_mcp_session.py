import asyncio
import os
import sys

# Ensure PYTHONPATH sees everything
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "mcp_core", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "agent_runtime", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "llm_client", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "memory_host_sdk", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "plugin_sdk", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "config_core", "src")))

from src.agents.sessions.sdk import create_agent_session, CreateAgentSessionOptions
from src.sessions.model_registry import ModelRegistry
from src.sessions.session_manager_in_memory import InMemorySessionManager

async def main():
    print("Testing MCP Tool injection into AgentSession...")
    cwd = os.getcwd()
    
    # We just need simple mock dependencies
    model_registry = ModelRegistry(registry_file=None)
    session_manager = InMemorySessionManager()
    
    # Needs settings_manager but we can mock it
    class MockSettingsManager:
        def get_steering_mode(self): return "all"
        def get_follow_up_mode(self): return "all"
        def get_transport(self): return "auto"
        def get_thinking_budgets(self): return None
        def get_provider_retry_settings(self): return {}
        def get_agent_defaults(self): return {}
    
    settings_manager = MockSettingsManager()
    
    options = CreateAgentSessionOptions(
        cwd=cwd,
        model_registry=model_registry,
        session_manager=session_manager,
        settings_manager=settings_manager,
        model={"provider": "google", "id": "gemini-2.0-flash"}
    )
    
    try:
        result = await create_agent_session(options)
        session = result["session"]
        
        tools = session.get_active_tool_names()
        print(f"Total tools injected: {len(tools)}")
        print(f"Tool names: {tools}")
        
        mcp_tools = [t for t in tools if t.startswith("mcp_")]
        if not mcp_tools:
            print("ERROR: No MCP tools found! Is test_everything configured?")
            return
            
        print(f"SUCCESS: Found MCP tools: {mcp_tools}")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
