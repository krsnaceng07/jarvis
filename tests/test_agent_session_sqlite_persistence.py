from pathlib import Path

from src.agents.sessions.session_manager import SessionManager


def test_sqlite_session_persists_and_reopens(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    persistence = {"agent_id": "main", "store_path": str(db_path)}
    manager = SessionManager.create(str(tmp_path), sqlite_persistence=persistence)
    session_id = manager.session_id
    manager.append_message({"role": "user", "content": "hello"})
    manager.append_message({"role": "assistant", "content": "world"})

    reopened = SessionManager.open(manager.session_file or "")

    assert reopened.session_id == session_id
    assert [
        entry["message"]["role"]
        for entry in reopened.file_entries
        if entry.get("type") == "message"
    ] == ["user", "assistant"]
