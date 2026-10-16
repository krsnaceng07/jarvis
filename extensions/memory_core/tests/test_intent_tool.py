import pytest
from extensions.memory_core.plugin import MemoryCorePlugin
from extensions.memory_core.runtime import MemoryRuntime


@pytest.mark.asyncio
async def test_intent_tool(tmp_path):
    # Setup runtime
    db_path = tmp_path / "memory.sqlite"
    runtime = MemoryRuntime(db_path)
    plugin = MemoryCorePlugin()

    # 1. List (should be empty initially)
    res = plugin._intent({"action": "list"}, runtime)
    assert res.is_ok
    assert "No standing intents found" in res.value

    # 2. Create an intent
    res = plugin._intent(
        {"action": "create", "condition": "If user asks about weather, check the location."},
        runtime,
    )
    assert res.is_ok
    assert "Created standing intent" in res.value

    # Extract intentId from output if possible, but let's just list and find it
    res = plugin._intent({"action": "list"}, runtime)
    assert res.is_ok
    assert "Standing intents:" in res.value
    assert "If user asks about weather, check the location." in res.value

    lines = res.value.split("\n")
    intent_id = lines[1].split("[")[1].split("]")[0]

    # 3. Cancel the intent
    res = plugin._intent({"action": "cancel", "intentId": intent_id}, runtime)
    assert res.is_ok
    assert "Cancelled intent" in res.value

    # Listing after cancellation
    res = plugin._intent({"action": "list"}, runtime)
    assert res.is_ok
    assert "No standing intents found" in res.value
