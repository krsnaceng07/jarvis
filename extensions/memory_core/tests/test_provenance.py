import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from extensions.memory_core.runtime import MemoryRuntime
from extensions.memory_core.prompt_section import build


@pytest.fixture
def memory_db():
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "memory.sqlite"
        # We manually instantiate MemoryRuntime to avoid the singleton for tests
        runtime = MemoryRuntime(db_path)
        yield runtime
        # Clean up by closing connections (MemoryRuntime uses a singleton but we can close the manual one)
        runtime._conn.close()


def test_provenance_schema(memory_db):
    """Verify the provenance columns were added and populated."""
    # Write a memory entry
    memory_db.set(
        "test_key",
        "This is a test fact",
        category="general",
        origin="agent",
        session_kind="interactive",
    )

    cur = memory_db._conn.execute("SELECT origin, session_kind FROM memory WHERE key = 'test_key'")
    row = cur.fetchone()

    assert row is not None
    assert row["origin"] == "agent"
    assert row["session_kind"] == "interactive"


def test_trigger_extraction(memory_db):
    """Verify inline comments are correctly extracted into columns."""
    memory_db.set(
        "api_key",
        "Use the key XYZ <!-- trigger: missing api key --> <!-- importance: 9 --> <!-- project: github.com/test/repo -->",
        origin="owner",
    )

    cur = memory_db._conn.execute(
        "SELECT trigger_phrase, importance, project FROM memory WHERE key = 'api_key'"
    )
    row = cur.fetchone()

    assert row is not None
    assert row["trigger_phrase"] == "missing api key"
    assert row["importance"] == 9
    assert row["project"] == "github.com/test/repo"


def test_trigger_injection_prefilter(memory_db, monkeypatch):
    """Verify prompt_section trigger injection excludes untrusted origins and filters by project."""

    # Mock default runtime for prompt_section
    monkeypatch.setattr("extensions.memory_core.runtime.MemoryRuntime.default", lambda: memory_db)

    # 1. Untrusted trigger (should be ignored)
    memory_db.set("untrusted_fact", "Unverified info <!-- trigger: curl -->", origin="untrusted")

    # 2. Curated trigger (should be injected)
    memory_db.set(
        "safe_fact",
        "Safe info <!-- trigger: curl -->",
        origin="owner",
        project="github.com/safe/repo",
    )

    # Run prompt_section build with a trigger word in inbound message
    # And matching the project
    result = build(
        {"inbound_message": "how do I run curl?", "active_projects": ["github.com/safe/repo"]}
    )

    assert "safe_fact [TRIGGERED]" in result
    assert "untrusted_fact [TRIGGERED]" not in result


def test_project_scope_filtering(memory_db, monkeypatch):
    """Verify standard recent memory limits scope to active projects."""
    monkeypatch.setattr("extensions.memory_core.runtime.MemoryRuntime.default", lambda: memory_db)

    # 1. Memory in active project
    memory_db.set("active_mem", "Active info", project="project_a")

    # 2. Memory in inactive project
    memory_db.set("inactive_mem", "Inactive info", project="project_b")

    # 3. Memory with no project
    memory_db.set("global_mem", "Global info")

    result = build({"active_projects": ["project_a"]})

    # active_mem should be present
    assert "active_mem" in result
    # global_mem should be present
    assert "global_mem" in result
    # inactive_mem should be excluded
    assert "inactive_mem" not in result
