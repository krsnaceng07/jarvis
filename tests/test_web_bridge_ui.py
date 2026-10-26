"""tests/test_web_bridge_ui.py — Tests for the React + TypeScript Web & Desktop Bridge."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest
from starlette.testclient import TestClient

from jarvis_desktop.web_bridge import JarvisWebUI


@pytest.fixture
def web_ui():
    return JarvisWebUI()


def test_web_ui_initial_state(web_ui: JarvisWebUI):
    assert web_ui.state == "INITIALISING"
    assert web_ui.muted is False
    assert web_ui.current_file is None


def test_web_ui_state_transition(web_ui: JarvisWebUI):
    web_ui.set_state("LISTENING")
    assert web_ui.state == "LISTENING"

    web_ui.set_state("THINKING")
    assert web_ui.state == "THINKING"

    web_ui.set_state("SPEAKING")
    assert web_ui.state == "SPEAKING"


def test_web_ui_muted_toggle(web_ui: JarvisWebUI):
    web_ui.muted = True
    assert web_ui.muted is True

    web_ui.muted = False
    assert web_ui.muted is False


def test_web_ui_write_log(web_ui: JarvisWebUI):
    web_ui.write_log("SYS: Test log message")
    assert len(web_ui._recent_logs) >= 1
    assert "Test log message" in web_ui._recent_logs[-1]["text"]


def test_web_ui_rest_status(web_ui: JarvisWebUI):
    client = TestClient(web_ui.app)
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ONLINE"
    assert "state" in data
    assert "model" in data


def test_web_ui_rest_modules(web_ui: JarvisWebUI):
    client = TestClient(web_ui.app)
    response = client.get("/api/modules")
    assert response.status_code == 200
    data = response.json()
    assert "MEMORY" in data
    assert "SKILLS" in data
    assert "CHARACTER" in data
    assert "SETTINGS" in data


def test_web_ui_chat_dispatch(web_ui: JarvisWebUI):
    mock_command = MagicMock()
    web_ui.on_text_command = mock_command

    client = TestClient(web_ui.app)
    response = client.post("/api/chat", json={"text": "status report"})
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_web_ui_websocket_flow(web_ui: JarvisWebUI):
    mock_command = MagicMock()
    web_ui.on_text_command = mock_command

    client = TestClient(web_ui.app)
    with client.websocket_connect("/ws/ui") as ws:
        # Initial handshake frame
        init_frame = ws.receive_json()
        assert init_frame["type"] == "init"
        assert "state" in init_frame
        assert "system_telemetry" in init_frame

        # Send a chat message
        ws.send_json({"action": "chat_message", "text": "Hello Jarvis"})
        chat_log = ws.receive_json()
        assert chat_log["type"] == "log"
        assert "Hello Jarvis" in chat_log["text"]

        chat_transcript = ws.receive_json()
        assert chat_transcript["type"] == "transcript"
        assert chat_transcript["clean_text"] == "Hello Jarvis"

        # Send mute toggle
        ws.send_json({"action": "set_muted", "muted": True})
        frame = ws.receive_json()
        assert frame["type"] == "muted"
        assert frame["muted"] is True
        assert web_ui.muted is True

        # Send terminate
        ws.send_json({"action": "terminate"})
        frame_state = ws.receive_json()
        assert frame_state["type"] == "state"
        assert frame_state["state"] == "STANDBY"
        assert web_ui.state == "STANDBY"


def test_web_ui_memories_endpoints(web_ui: JarvisWebUI):
    client = TestClient(web_ui.app)
    # 1. Fetch memories
    resp = client.get("/api/memories")
    assert resp.status_code == 200
    data = resp.json()
    assert "memories" in data
    assert isinstance(data["memories"], list)

    # 2. Add memory
    post_resp = client.post("/api/memories", json={"key": "Test Preference", "value": "Dark theme enabled", "category": "user"})
    assert post_resp.status_code == 200
    created = post_resp.json()
    assert created.get("success") is True or "id" in created

    # 3. Delete memory
    del_resp = client.delete("/api/memories/test-mem-id")
    assert del_resp.status_code == 200
    assert del_resp.json().get("success") is True


def test_web_ui_skills_endpoints(web_ui: JarvisWebUI):
    client = TestClient(web_ui.app)
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert "skills" in data
    assert len(data["skills"]) > 0
    # Check shape of a skill
    first_skill = data["skills"][0]
    assert "name" in first_skill
    assert "description" in first_skill


def test_web_ui_tasks_endpoints(web_ui: JarvisWebUI):
    client = TestClient(web_ui.app)
    resp = client.get("/api/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert "tasks" in data
    assert isinstance(data["tasks"], list)

    # Cancel task
    cancel_resp = client.post("/api/tasks/cancel", json={"taskId": "task-01"})
    assert cancel_resp.status_code == 200
    assert cancel_resp.json().get("success") is True


def test_web_ui_notes_endpoints(web_ui: JarvisWebUI):
    client = TestClient(web_ui.app)
    # 1. Fetch notes
    resp = client.get("/api/notes")
    assert resp.status_code == 200
    data = resp.json()
    assert "notes" in data

    # 2. Add note
    post_resp = client.post("/api/notes", json={
        "id": "test-note-1",
        "title": "Quantum Computation",
        "content": "Superconducting qubits with 99.9% fidelity.",
        "tags": ["Quantum", "Physics"]
    })
    assert post_resp.status_code == 200
    assert post_resp.json().get("success") is True

    # 3. Delete note
    del_resp = client.delete("/api/notes/test-note-1")
    assert del_resp.status_code == 200
    assert del_resp.json().get("success") is True


def test_web_ui_headlines_endpoints(web_ui: JarvisWebUI):
    client = TestClient(web_ui.app)
    resp = client.get("/api/headlines")
    assert resp.status_code == 200
    data = resp.json()
    assert "headlines" in data
    assert len(data["headlines"]) > 0
    first = data["headlines"][0]
    assert "title" in first
    assert "timestamp" in first


def test_web_ui_settings_endpoints(web_ui: JarvisWebUI):
    client = TestClient(web_ui.app)
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "model" in data
    assert "theme" in data
    assert "gateway_port" in data


def test_web_ui_upload_endpoints(web_ui: JarvisWebUI):
    mock_command = MagicMock()
    web_ui.on_text_command = mock_command

    client = TestClient(web_ui.app)
    resp = client.post("/api/upload", json={
        "filename": "test_document.txt",
        "content_base64": "SGVsbG8gSmFydmlzIQ=="
    })
    assert resp.status_code == 200
    assert resp.json().get("success") is True
    assert mock_command.called

