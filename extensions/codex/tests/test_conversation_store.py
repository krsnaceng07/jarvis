from __future__ import annotations

from pathlib import Path

from extensions.codex.src.conversation_store import CodexConversationStore


def test_codex_conversation_state_survives_store_recreation(tmp_path):
    db_path = tmp_path / "jarvis.sqlite"
    first = CodexConversationStore(db_path)
    first.update_binding(
        "session-1",
        {"threadId": "thread-1", "cwd": "E:/jarvis", "model": "gpt-live", "provider": "codex"},
    )
    first.update_state("session-1", {"fast": True, "permissions": "default"})

    second = CodexConversationStore(db_path)
    assert second.read_binding("session-1") == {
        "threadId": "thread-1",
        "cwd": "E:/jarvis",
        "model": "gpt-live",
        "provider": "codex",
    }
    assert second.read_state("session-1") == {"fast": True, "permissions": "default"}


def test_detaching_binding_preserves_conversation_preferences(tmp_path):
    store = CodexConversationStore(tmp_path / "jarvis.sqlite")
    store.update_state("session-1", {"fast": False, "permissions": "yolo"})
    store.update_binding("session-1", {"threadId": "thread-1", "provider": "codex"})
    store.update_binding("session-1", None)

    assert store.read_binding("session-1") is None
    assert store.read_state("session-1") == {"fast": False, "permissions": "yolo"}


def test_session_callbacks_match_command_context_contract(tmp_path):
    store = CodexConversationStore(tmp_path / "jarvis.sqlite")
    callbacks = store.callbacks("session-1")

    callbacks["binding_update_fn"]({"threadId": "thread-1", "provider": "codex"})
    callbacks["state_update_fn"]({"fast": True})

    assert store.read_binding("session-1")["threadId"] == "thread-1"
    assert callbacks["state_read_fn"]() == {"fast": True}


def test_store_defaults_to_canonical_state_database(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))

    CodexConversationStore().update_state("session-1", {"fast": True})

    assert (Path(tmp_path) / "jarvis.sqlite").exists()
