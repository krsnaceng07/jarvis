import asyncio
import os
import sys

# Ensure we can import from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.agents.sessions.tools.exec_tool import create_exec_tool_definition

class MockContext:
    class MockPermissions:
        mode = "restrictive"
    permissions = MockPermissions()

async def main():
    exec_def = create_exec_tool_definition(cwd=os.getcwd())
    execute = exec_def["execute"]
    
    # Try running an allowed command (if there is one in the mocked profiles)
    print("Testing an allowed command: ls")
    try:
        res = await execute("id1", {"command": "ls -l"}, ctx=MockContext())
        print("ls executed successfully.", res)
    except Exception as e:
        print("ls failed:", e)

    print("\nTesting blocked safeBin command: jq")
    try:
        res = await execute("id2", {"command": "jq ."}, ctx=MockContext())
        print("jq executed successfully.", res)
    except Exception as e:
        print("jq blocked as expected:", e)

    print("\nTesting safeBin with malicious flags: sed -e")
    try:
        res = await execute("id3", {"command": "sed -e 's/a/b/'"}, ctx=MockContext())
        print("sed executed successfully.", res)
    except Exception as e:
        print("sed blocked as expected:", e)

if __name__ == "__main__":
    asyncio.run(main())
