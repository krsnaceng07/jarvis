"""Test suite for JARVIS restart persistence, voice memory grounding, and channel prompt continuity.

Verifies OpenClaw parity:
1. Voice grounding: 'save_memory' allowed on explicit English/Nepali memory intent, blocked on vague speech.
2. Canonical memory persistence: 'save_fact' writes to canonical ~/.jarvis/core/memory.sqlite, immediately discoverable by load_memory().
3. Dialogue history continuity: session transcripts recorded to SQLite and restored to HUD activity log upon restart.
4. Channel prompt continuity: configured messaging channels are injected into LiveConnectConfig system instructions so the model never prompts for tokens again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.desktop.src.jarvis_desktop.memory_bridge import (
    format_memory_for_prompt,
    load_memory,
    save_fact,
)
from src.agents.task.session_transcript_store import SessionTranscriptStore
from src.channels.channel_manager import ChannelManager
from src.talk.speech_guard import SpeechGroundingGuard


def test_speech_grounding_save_memory_nepali_and_english():
    """Verify that speech grounding approves save_memory for clear intent and blocks vague speech."""
    guard = SpeechGroundingGuard()

    # Nepali intents must be grounded
    res1 = guard.validate_voice_tool_call("save_memory", {"category": "identity", "key": "name", "value": "Krishna"}, "mero naam Krishna ho yaad rakh")
    assert res1.is_allowed is True, f"Blocked: {res1.reason}"

    res2 = guard.validate_voice_tool_call("save_memory", {"category": "preferences", "key": "food", "value": "momo"}, "melai momo manparcha yaad rakhnu")
    assert res2.is_allowed is True, f"Blocked: {res2.reason}"

    res3 = guard.validate_voice_tool_call("save_memory", {"category": "identity", "key": "city", "value": "Kathmandu"}, "mero ghar Kathmandu ho save gara")
    assert res3.is_allowed is True, f"Blocked: {res3.reason}"

    # English intents must be grounded
    res4 = guard.validate_voice_tool_call("save_memory", {"category": "preferences", "key": "color", "value": "blue"}, "remember that my favorite color is blue")
    assert res4.is_allowed is True, f"Blocked: {res4.reason}"

    res5 = guard.validate_voice_tool_call("save_memory", {"category": "notes", "key": "item", "value": "jarvis"}, "save to memory: jarvis project")
    assert res5.is_allowed is True, f"Blocked: {res5.reason}"

    # Vague or incomplete speech must be blocked
    res_vague1 = guard.validate_voice_tool_call("save_memory", {"key": "x"}, "i was thinking")
    assert res_vague1.is_allowed is False

    res_vague2 = guard.validate_voice_tool_call("save_memory", {"key": "x"}, "maybe we should check")
    assert res_vague2.is_allowed is False

    res_vague3 = guard.validate_voice_tool_call("save_memory", {"key": "x"}, "hmm")
    assert res_vague3.is_allowed is False


def test_canonical_memory_persistence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify save_fact writes to canonical SQLite runtime and load_memory reads it."""
    fake_data_dir = tmp_path / "jarvis_data"
    fake_core = fake_data_dir / "core"
    fake_core.mkdir(parents=True)
    monkeypatch.setenv("JARVIS_DATA_DIR", str(fake_data_dir))

    # Save a fact
    result = save_fact(
        category="identity",
        key="user_name",
        value="Krishna",
        workspace_dir=tmp_path,
    )
    assert result.get("status") != "rejected"

    # Verify canonical SQLite contains the fact
    mem = load_memory()
    assert "identity" in mem
    assert "user_name" in mem["identity"]
    assert "Krishna" in mem["identity"]["user_name"]["value"]

    # Verify prompt formatting includes the fact
    formatted = format_memory_for_prompt(mem, workspace_dir=tmp_path)
    assert "user_name: Krishna" in formatted


def test_session_transcript_continuity_across_restart(tmp_path: Path):
    """Verify turns are stored in SQLite and can be restored across restarts."""
    db_path = tmp_path / "test_agent.sqlite"
    store = SessionTranscriptStore(db_path=db_path)

    # Simulate turns in previous session
    store.append_entry("desktop:hud", "user_speech", {"text": "नमस्ते जारभिस, के छ खबर?"})
    store.append_entry("desktop:hud", "assistant_speech", {"text": "नमस्ते सर, म एकदम ठीक छु। हजुरलाई कसरी सहयोग गर्न सक्छु?"})
    store.append_entry("desktop:hud", "user_turn", {"text": "mero naam Krishna ho yaad rakh"})
    store.append_entry("desktop:hud", "assistant_speech", {"text": "मैले सम्झिएँ सर, हजुरको नाम कृष्ण हो।"})

    # Simulate restart with fresh store instance pointing to same SQLite database
    restart_store = SessionTranscriptStore(db_path=db_path)
    entries = restart_store.get_recent_entries("desktop:hud", limit=10)
    assert len(entries) == 4

    user_texts = [e["data"]["text"] for e in entries if e["entry_type"] in ("user_speech", "user_turn")]
    assistant_texts = [e["data"]["text"] for e in entries if e["entry_type"] == "assistant_speech"]

    assert "नमस्ते जारभिस, के छ खबर?" in user_texts
    assert "mero naam Krishna ho yaad rakh" in user_texts
    assert "मैले सम्झिएँ सर, हजुरको नाम कृष्ण हो।" in assistant_texts


def test_channel_status_prompt_formatting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify ChannelManager generates prompt context for active/enabled channels."""
    fake_data_dir = tmp_path / "jarvis_data"
    fake_data_dir.mkdir(parents=True)
    monkeypatch.setenv("JARVIS_DATA_DIR", str(fake_data_dir))

    # Write config with telegram channel
    cfg_file = fake_data_dir / "config.json"
    cfg_file.write_text(
        """{
            "channels": {
                "telegram": {
                    "enabled": true,
                    "botToken": "12345:ABCDEF",
                    "botUsername": "Jarvissagentbot",
                    "dmPolicy": "open"
                }
            }
        }""",
        encoding="utf-8",
    )

    mgr = ChannelManager()
    prompt_snippet = mgr.format_channel_status_for_prompt()

    assert "[CONFIGURED EXTERNAL MESSAGING CHANNELS]" in prompt_snippet
    assert "Channel 'telegram'" in prompt_snippet
    assert "@Jarvissagentbot" in prompt_snippet
    assert "Do NOT ask the user for bot tokens" in prompt_snippet
