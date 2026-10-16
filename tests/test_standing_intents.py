import pytest
from extensions.memory_core.runtime import MemoryRuntime

@pytest.fixture
def memory_runtime(tmp_path):
    db_path = tmp_path / "test_memory.sqlite"
    runtime = MemoryRuntime(db_path)
    yield runtime
    runtime.close()

def test_intent_lifecycle(memory_runtime: MemoryRuntime):
    # 1. Create an intent
    res = memory_runtime.create_intent(
        description="If user asks about weather, check the location.",
        trigger_keywords="weather, location",
        expiry_days=90,
        cooldown_hours=24,
        max_fires=3
    )
    assert "Created standing intent" in res

    # 2. List intents
    listing = memory_runtime.list_intents()
    assert "If user asks about weather, check the location." in listing
    assert "0/3 fires" in listing
    assert "armed" in listing

    # 3. Test matching prefilter (hit)
    hit = memory_runtime.get_triggered_intents("I want to know the weather for my location.")
    assert len(hit) == 1
    # Note: get_triggered_intents returns the state *before* the mutation, or *after*?
    # Wait, get_triggered_intents returns the `row` from the SELECT before UPDATE.
    # But let's check it in listing anyway.

    # 4. Test missing keywords (miss)
    miss = memory_runtime.get_triggered_intents("I want to know the time.")
    assert len(miss) == 0

    # 5. List after firing (should be fired, 1/3 fires)
    listing_after = memory_runtime.list_intents()
    assert "1/3 fires" in listing_after
    assert "fired" in listing_after
    
    # 6. Cancel the intent
    intent_id = hit[0]["id"]
    memory_runtime.cancel_intent(intent_id)
    listing_default = memory_runtime.list_intents()
    assert "No standing intents found." in listing_default
    listing_cancelled = memory_runtime.list_intents(include_cancelled=True)
    assert "cancelled" in listing_cancelled
