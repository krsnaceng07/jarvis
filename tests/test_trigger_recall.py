from extensions.memory_core.runtime import MemoryRuntime

def test_trigger_recall_trusted_entries_only(tmp_path):
    # Setup test DB
    db_path = tmp_path / "memory.sqlite"
    runtime = MemoryRuntime(db_path=db_path)
    
    # Inject 3 triggered entries: one MEMORY.md, one USER.md, one memory/2026-08-14.md
    with runtime._conn_lock:
        runtime._conn.execute(
            """
            INSERT INTO memory (key, value, category, trigger_phrase, origin, project, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("MEMORY.md", "I love apples", "preference", "apples", "user", None, 100)
        )
        runtime._conn.execute(
            """
            INSERT INTO memory (key, value, category, trigger_phrase, origin, project, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("USER.md", "I hate oranges", "preference", "oranges", "user", None, 200)
        )
        runtime._conn.execute(
            """
            INSERT INTO memory (key, value, category, trigger_phrase, origin, project, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("memory/2026-08-14.md", "Random note about apples", "fact", "apples", "user", None, 300)
        )
        
    hits = runtime.get_triggered_memory("apples oranges", active_projects=None, limit=3)
    
    assert len(hits) == 2
    keys = {h["key"] for h in hits}
    assert "MEMORY.md" in keys
    assert "USER.md" in keys
    assert "memory/2026-08-14.md" not in keys
