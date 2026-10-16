import pytest

from src.agents.tool_search import ToolSearchRuntime
from src.agents.tool_policy import build_tool_search_run_plan


@pytest.fixture
def dummy_catalog():
    class DummyCatalog:
        def get_effective_inventory(self):
            class DummyTool:
                def __init__(self, name, desc):
                    self.name = name
                    self.description = desc
                    self.parameters_schema = {}

            return [
                DummyTool("file_read", "Read a file from disk"),
                DummyTool("web_search", "Search the web for information"),
                DummyTool("exec", "Run a shell command"),
            ]

        def get(self, name):
            tools = {t.name: t for t in self.get_effective_inventory()}
            tool = tools.get(name)
            if tool:
                tool.quarantined = False
            return tool

    return DummyCatalog()


def test_tool_search_bm25_ranking(dummy_catalog):
    search_runtime = ToolSearchRuntime(catalog=dummy_catalog)

    # Test search ranking
    results = search_runtime.search("read files from disk")
    assert len(results) > 0
    assert results[0]["name"] == "file_read"

    results2 = search_runtime.search("search internet web")
    assert len(results2) > 0
    assert results2[0]["name"] == "web_search"


def test_tool_search_code_bridge():
    # Test the subprocess Node.js bridge
    class MockCatalog:
        def get_effective_inventory(self):
            class DummyTool:
                def __init__(self, name, desc):
                    self.name = name
                    self.description = desc
                    self.parameters_schema = {}

            return [DummyTool("mock_tool", "A mock tool")]

        def get(self, name):
            if name == "mock_tool":

                class DummyTool:
                    def __init__(self, name, desc):
                        self.name = name
                        self.description = desc
                        self.parameters_schema = {}
                        self.quarantined = False

                return DummyTool("mock_tool", "A mock tool")
            return None

    def execute_tool(name, args):
        return {"result": f"mock result for {name}"}

    search_runtime = ToolSearchRuntime(catalog=MockCatalog(), execute_tool_callback=execute_tool)

    code = """
    console.log("Searching...");
    const results = await openclaw.tools.search("mock");
    if (results.length === 0 || results[0].name !== "mock_tool") {
        throw new Error("Search failed");
    }
    
    console.log("Calling...");
    const result = await openclaw.tools.call("mock_tool", { arg: 1 });
    return result;
    """

    # We will use the built-in run_code_mode inside the search_runtime
    result = search_runtime.run_code_mode(code)

    # _run_code_mode returns a dict containing result/logs/stderr
    assert result.get("result", {}).get("ok") is True
    assert "mock result for mock_tool" in str(result.get("result", {}).get("value"))


def test_build_tool_search_run_plan():
    plan = build_tool_search_run_plan(
        visible_tools=["tool_search", "exec"],
        uncompacted_tools=["tool_search", "file_read", "exec"],
        controls_enabled=True,
    )

    assert "tool_search" in plan.visible_allowed_tool_names
    assert "file_read" not in plan.visible_allowed_tool_names

    # Now test without controls
    plan2 = build_tool_search_run_plan(
        visible_tools=["file_read", "exec"],
        uncompacted_tools=["file_read", "exec"],
        controls_enabled=False,
    )
    assert "file_read" in plan2.visible_allowed_tool_names
