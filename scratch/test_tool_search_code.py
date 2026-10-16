import asyncio

from src.agents.tool_search_code_runner import ToolSearchCodeRunner

async def main():
    def search(query):
        return [{"name": "mock_tool", "description": "A mock tool", "score": 1.0}]
    
    def describe(name):
        if name == "mock_tool":
            return {"name": "mock_tool", "description": "A mock tool", "parameters": {}}
        return None
    
    def call(name, args):
        print(f"Called {name} with args {args}")
        return {"result": f"called {name}"}

    runner = ToolSearchCodeRunner(
        search=search,
        describe=describe,
        call=call,
        log=lambda t, m: print(f"[{t}] {m}")
    )
    
    code = """
    console.log("Searching...");
    const results = await openclaw.tools.search("test query");
    console.log("Results: " + JSON.stringify(results));
    
    console.log("Describing...");
    const desc = await openclaw.tools.describe("mock_tool");
    console.log("Desc: " + JSON.stringify(desc));
    
    console.log("Calling...");
    const result = await openclaw.tools.call("mock_tool", { arg1: "value1" });
    console.log("Call result: " + JSON.stringify(result));
    
    return { "success": true, "result": result };
    """
    
    print("Running code...")
    result, error = await runner.run_code(code)
    print("Result:", result)
    print("Error:", error)
    
if __name__ == "__main__":
    asyncio.run(main())
