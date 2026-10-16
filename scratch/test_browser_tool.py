import asyncio
import sys
import os
import glob

# Dynamically add all workspace packages to sys.path
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for src_dir in glob.glob(os.path.join(workspace_root, "packages", "*", "src")):
    sys.path.append(src_dir)
sys.path.append(os.path.join(workspace_root, "src"))
sys.path.append(workspace_root)

from extensions.browser.src.browser_tool import BrowserTool
from extensions.browser.src.browser_tool_schema import BrowserToolInput
from extensions.browser.src.config import BrowserConfig
from extensions.browser.src.browser_profiles import resolve_browser_config

class MockPluginState:
    def __init__(self, state):
        self._state = state
    def get(self, key):
        return self._state.get(key)

class MockContext:
    def __init__(self, config):
        self.plugin_state = MockPluginState({"browser_config": config})

async def main():
    print("Resolving browser config...")
    raw_cfg = BrowserConfig(enabled=True, profiles={"openclaw": {"driver": "openclaw", "headless": True}})
    resolved = resolve_browser_config(raw_cfg)
    ctx = MockContext(resolved)
    
    print("Instantiating BrowserTool...")
    tool = BrowserTool()
    
    # Check if tool has execute method
    if not hasattr(tool, "execute"):
        print("Error: BrowserTool has no execute method")
        return
        
    print("Calling execute to navigate to a page and get title...")
    input_data = BrowserToolInput(
        profile="openclaw",
        action="navigate",
        url="https://example.com"
    )
    
    result = await tool.execute(ctx, input_data)
    print(f"Goto Result: {result}")
    
    if result.is_ok:
        print("Calling execute to extract page title...")
        input_data2 = BrowserToolInput(
            profile="openclaw",
            action="snapshot"
        )
        result2 = await tool.execute(ctx, input_data2)
        print(f"Extract Result: {result2}")
        
    print("Stopping browser runtime...")
    # Clean up the browser runtime which is cached globally in get_browser_runtime
    from extensions.browser.src.browser_runtime import get_browser_runtime
    runtime = get_browser_runtime(resolved)
    await runtime.stop()

if __name__ == "__main__":
    asyncio.run(main())
