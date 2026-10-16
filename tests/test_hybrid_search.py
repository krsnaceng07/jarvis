import pytest
import datetime
from extensions.memory_core.hybrid_search import HybridSearchEngine

class MockSQLiteRuntime:
    def search_text(self, query, limit):
        return [
            {
                "key": "memory/2026-08-01.md",
                "value": "This is a dated memory entry. About dogs.",
                "category": "general"
            },
            {
                "key": "MEMORY.md",
                "value": "This is an evergreen memory entry. About cats.",
                "category": "preference"
            },
            {
                "key": "memory/2020-01-01.md",
                "value": "Very old entry. About cats and dogs.",
                "category": "fact"
            },
            {
                "key": "USER.md",
                "value": "This is a duplicated evergreen entry. About cats.",
                "category": "preference"
            }
        ]
        
    def search_substring(self, query, limit):
        return []

@pytest.mark.asyncio
async def test_hybrid_search_scoring(monkeypatch):
    sqlite = MockSQLiteRuntime()
    engine = HybridSearchEngine(sqlite)
    
    # Mock datetime to a specific date for deterministic testing
    class MockDatetime:
        @classmethod
        def now(cls):
            return datetime.datetime(2026, 8, 14)
        @classmethod
        def strptime(cls, date_str, fmt):
            return datetime.datetime.strptime(date_str, fmt)
            
    monkeypatch.setattr("extensions.memory_core.hybrid_search.datetime", MockDatetime)
    
    # Mock get_active_memory_search_manager to return None (testing BM25 path only)
    async def mock_get_manager(params):
        return None
    monkeypatch.setattr("extensions.memory_core.hybrid_search.get_active_memory_search_manager", mock_get_manager)
    
    results = await engine.search(query="dogs", agent_id="default", max_results=4, min_score=0.0)
    
    assert len(results) > 0
    # MEMORY.md should have no decay
    mem_md = next(r for r in results if r["key"] == "MEMORY.md")
    assert mem_md["base_score"] == 0.5 # substring match roughly
    
    # 2026-08-01 should have slight decay (13 days old -> ~0.74 multiplier)
    aug_1 = next(r for r in results if r["key"] == "memory/2026-08-01.md")
    assert aug_1["final_score"] < 0.5
    assert aug_1["final_score"] > 0.3
    
    # 2020-01-01 should have massive decay
    jan_1 = next(r for r in results if r["key"] == "memory/2020-01-01.md")
    assert jan_1["final_score"] < 0.1
    
    # Check MMR: USER.md is very similar to MEMORY.md, it should be penalized
    user_md = next((r for r in results if r["key"] == "USER.md"), None)
    # With lambda 0.7, similarity penalty might push it down or out
    if user_md:
        # It's in the results, but should be ranked lower than MEMORY.md despite equal base scores
        mem_idx = results.index(mem_md)
        user_idx = results.index(user_md)
        assert mem_idx < user_idx
