import pytest
from src.agents.sessions.context_pruning import apply_context_pruning

@pytest.fixture
def base_messages():
    return [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
        {"role": "user", "content": "Do some work"},
        {"role": "assistant", "content": "Okay"},
        {"role": "toolResult", "name": "work_tool", "content": "This is a short result."},
        {"role": "assistant", "content": "Got it"},
        {"role": "user", "content": "Do a lot of work"},
        {
            "role": "toolResult", 
            "name": "large_tool", 
            "content": "A" * 10000
        },
        {"role": "assistant", "content": "Done"}
    ]

def test_pruning_skipped_if_ttl_not_expired(base_messages):
    config = {"mode": "cache-ttl", "ttl": "5m"}
    new_messages, new_time, modified = apply_context_pruning(
        messages=base_messages,
        prune_config=config,
        last_pruned_time=0.0,
        current_time=100.0,  # 100 seconds < 300 seconds
        max_context_window=100000
    )
    assert not modified
    assert new_time == 0.0

def test_pruning_skipped_if_context_small(base_messages):
    config = {"mode": "cache-ttl", "ttl": "5m"}
    new_messages, new_time, modified = apply_context_pruning(
        messages=base_messages,
        prune_config=config,
        last_pruned_time=0.0,
        current_time=600.0,
        max_context_window=1000000  # huge window
    )
    assert not modified

def test_soft_trimming_applied(base_messages):
    config = {"mode": "cache-ttl", "ttl": "5m"}
    # Need to manipulate messages so large_tool is not in protected window
    msgs = base_messages + [{"role": "assistant", "content": "1"}, {"role": "assistant", "content": "2"}, {"role": "assistant", "content": "3"}]
    
    new_messages, new_time, modified = apply_context_pruning(
        messages=msgs,
        prune_config=config,
        last_pruned_time=0.0,
        current_time=600.0,
        max_context_window=10000 # 30% is 3000 chars, total chars > 10000 so it triggers
    )
    
    assert modified
    assert new_time == 600.0
    # large_tool is at index 7
    large_result = new_messages[7]["content"]
    assert "..." in large_result
    assert len(large_result) == 3000 + 5 # 1500 + \n...\n + 1500

def test_hard_clear_applied(base_messages):
    config = {"mode": "cache-ttl", "ttl": "5m", "hardClear": {"enabled": True, "placeholder": "[Cleared]"}}
    msgs = list(base_messages)
    # Add 20 tools of 3000 chars (will not be soft trimmed since limit is 4000, but they sum to 60000 which > 50000)
    for i in range(20):
        msgs.append({"role": "toolResult", "name": f"tool_{i}", "content": "A" * 3000})
    # Add 3 assistant turns to push it out of protected window
    msgs += [{"role": "assistant", "content": "1"}, {"role": "assistant", "content": "2"}, {"role": "assistant", "content": "3"}]
    
    new_messages, new_time, modified = apply_context_pruning(
        messages=msgs,
        prune_config=config,
        last_pruned_time=0.0,
        current_time=600.0,
        max_context_window=100000
    )
    
    assert modified
    # Check the first inserted tool is cleared
    # base_messages has 9 items, so the first inserted tool is at index 9
    assert new_messages[9]["content"] == "[Cleared]"

def test_legacy_image_cleanup():
    config = {"mode": "cache-ttl", "ttl": "5m"}
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "look"}, {"type": "image", "url": "data:image/png;base64,123"}]},
        {"role": "assistant", "content": "seen"},
        {"role": "user", "content": "[media attached: 1.png]"},
        {"role": "assistant", "content": "seen again"},
        {"role": "user", "content": "dummy"},
        {"role": "assistant", "content": "1"},
        {"role": "assistant", "content": "2"},
        {"role": "assistant", "content": "3"},
    ]
    
    new_messages, new_time, modified = apply_context_pruning(
        messages=msgs,
        prune_config=config,
        last_pruned_time=0.0,
        current_time=600.0,
        max_context_window=1000000 # Won't trigger normal pruning, but image cleanup ALWAYS runs if modified
    )
    assert modified
    # Check image removal
    assert new_messages[0]["content"][1]["text"] == "[image data removed - already processed by model]"
    assert new_messages[2]["content"] == "[media reference removed - already processed by model]"
