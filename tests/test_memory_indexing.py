import pytest
from extensions.memory_core.runtime import MemoryRuntime
from extensions.memory_core.memory_indexer import index_memory_files

@pytest.fixture
def workspace_with_memory(tmp_path):
    # Create MEMORY.md
    mem_file = tmp_path / "MEMORY.md"
    mem_file.write_text("This is the main memory file.\n\n" * 50) # 1500 chars
    
    # Create USER.md
    user_file = tmp_path / "USER.md"
    user_file.write_text("User prefers Python.\n" * 5)
    
    # Create memory/*.md
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    (mem_dir / "project_a.md").write_text("Project A docs here. <!-- importance: 5 --> <!-- trigger: project A -->")
    
    db_path = tmp_path / "core" / "memory.sqlite"
    runtime = MemoryRuntime(db_path)
    
    yield tmp_path, runtime
    
    runtime.close()

def test_memory_indexer(workspace_with_memory):
    workspace, runtime = workspace_with_memory
    
    total_chunks = index_memory_files(str(workspace), runtime)
    
    assert total_chunks > 0
    assert runtime.count() > 0
    
    # Check that MEMORY.md was chunked
    mem_chunks = runtime.search_substring("main memory file", limit=10)
    assert len(mem_chunks) > 0
    assert "MEMORY.md:0" in mem_chunks[0]["key"]
    
    # Check that USER.md was chunked
    user_chunks = runtime.search_substring("Python", limit=10)
    assert len(user_chunks) > 0
    assert "USER.md:0" in user_chunks[0]["key"]
    
    # Check that metadata was extracted from memory/project_a.md
    with runtime._conn_lock:
        row = runtime._conn.execute("SELECT importance, trigger_phrase FROM memory WHERE key LIKE 'memory/project_a.md%'").fetchone()
        assert row is not None
        assert row["importance"] == 5
        assert row["trigger_phrase"] == "project A"
        
    # Reindex should wipe out old chunks and recreate them without duplicating
    total_chunks_2 = index_memory_files(str(workspace), runtime)
    assert total_chunks_2 == total_chunks
    assert runtime.count() == total_chunks
