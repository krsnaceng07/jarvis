"""Unit tests for Voice Call runtime sessions, TTS engine, realtime, and streaming audio."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest


from extensions.voice_call.src.audio.agent_context import build_agent_voice_context_capsule
from extensions.voice_call.src.audio.fast_context import search_fast_context
from extensions.voice_call.src.audio.realtime_engine import RealtimeVoiceEngine
from extensions.voice_call.src.audio.realtime_tools import (
    execute_realtime_tool,
    get_consult_policy_guidance,
    get_realtime_tools_definitions,
)
from extensions.voice_call.src.audio.streaming_engine import StreamingTranscriptionEngine
from extensions.voice_call.src.audio.tts_engine import TTSEngine
from extensions.voice_call.src.config import (
    VoiceCallAgentContextConfig,
    VoiceCallConfig,
    VoiceCallRealtimeConfig,
    VoiceCallStreamingConfig,
    VoiceCallTTSConfig,
    validate_provider_config,
)
from extensions.voice_call.src.runtime import VoiceCallRuntime
from extensions.voice_call.src.types import CallSession, CallTurn


def test_validate_provider_config_constraints() -> None:
    # 1. realtime + inboundPolicy: disabled rejected
    cfg_rt_dis = VoiceCallConfig(
        enabled=True,
        inbound_policy="disabled",
        realtime=VoiceCallRealtimeConfig(enabled=True),
    )
    res_rt_dis = validate_provider_config(cfg_rt_dis)
    assert res_rt_dis.is_err
    assert "inboundPolicy must not be 'disabled'" in (res_rt_dis.error or "")

    # 2. realtime + streaming simultaneously rejected
    cfg_dual = VoiceCallConfig(
        enabled=True,
        inbound_policy="open",
        realtime=VoiceCallRealtimeConfig(enabled=True),
        streaming=VoiceCallStreamingConfig(enabled=True),
    )
    res_dual = validate_provider_config(cfg_dual)
    assert res_dual.is_err
    assert "cannot be combined with streaming.enabled" in (res_dual.error or "")

    # 3. streaming on non-twilio provider rejected
    cfg_st_mock = VoiceCallConfig(
        enabled=True,
        provider="mock",
        streaming=VoiceCallStreamingConfig(enabled=True),
    )
    res_st_mock = validate_provider_config(cfg_st_mock)
    assert res_st_mock.is_err
    assert "requires provider: twilio" in (res_st_mock.error or "")

    # 4. Valid realtime config accepted
    cfg_rt_ok = VoiceCallConfig(
        enabled=True,
        provider="twilio",
        inbound_policy="allowlist",
        realtime=VoiceCallRealtimeConfig(enabled=True),
    )
    assert validate_provider_config(cfg_rt_ok).is_ok

    # 5. Valid streaming config accepted
    cfg_st_ok = VoiceCallConfig(
        enabled=True,
        provider="twilio",
        streaming=VoiceCallStreamingConfig(enabled=True),
    )
    assert validate_provider_config(cfg_st_ok).is_ok


def test_agent_context_capsule_builder() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "SOUL.md").write_text("Soul essence: helpful and wise.", encoding="utf-8")
        (root / "IDENTITY.md").write_text("Identity: JARVIS core assistant.", encoding="utf-8")
        (root / "USER.md").write_text("User: Tony Stark.", encoding="utf-8")

        # Disabled returns empty string
        cfg_disabled = VoiceCallAgentContextConfig(enabled=False)
        assert build_agent_voice_context_capsule(cfg_disabled, workspace_root=root) == ""

        # Enabled builds capsule
        cfg_enabled = VoiceCallAgentContextConfig(
            enabled=True,
            max_chars=2000,
            include_identity=True,
            include_workspace_files=True,
            files=["SOUL.md", "IDENTITY.md", "USER.md"],
        )
        capsule = build_agent_voice_context_capsule(
            cfg_enabled, workspace_root=root, agent_id="jarvis-prime"
        )
        assert "[AGENT IDENTITY]" in capsule
        assert "jarvis-prime" in capsule
        assert "[WORKSPACE CAPSULE]" in capsule
        assert "Soul essence: helpful and wise." in capsule
        assert "User: Tony Stark." in capsule


def test_consult_policy_guidance() -> None:
    assert "Handle simple conversational greetings" in get_consult_policy_guidance("substantive")
    assert "before answering every substantive question" in get_consult_policy_guidance("always")
    assert "whenever deeper reasoning" in get_consult_policy_guidance("auto")


def test_realtime_tools_definitions_and_policies() -> None:
    # safe-read-only exposes end-call and agent-consult
    tools_safe = get_realtime_tools_definitions(tool_policy="safe-read-only")
    names_safe = [t["name"] for t in tools_safe]
    assert "openclaw_end_call" in names_safe
    assert "openclaw_agent_consult" in names_safe

    # none policy hides agent-consult but keeps end-call
    tools_none = get_realtime_tools_definitions(tool_policy="none")
    names_none = [t["name"] for t in tools_none]
    assert "openclaw_end_call" in names_none
    assert "openclaw_agent_consult" not in names_none


@pytest.mark.asyncio
async def test_realtime_tool_execution_and_fast_context() -> None:
    session = CallSession(
        id="c_tools",
        provider="mock",
        from_number="+155501",
        to_number="+155502",
        direction="inbound",
        agent_id="test-agent",
    )
    session.transcript.append(
        CallTurn(speaker="user", text="What is my account balance?", timestamp=100.0)
    )

    # 1. Execute end_call
    res_end = await execute_realtime_tool(
        tool_name="openclaw_end_call",
        arguments={},
        session=session,
    )
    assert res_end["status"] == "ended"
    assert session.status == "completed"

    # 2. Fast context keyword search
    fc_res = await search_fast_context(
        query="account balance",
        session=session,
        timeout_ms=1500,
        fallback_to_consult=True,
    )
    assert fc_res["found"] is True
    assert len(fc_res["snippets"]) > 0
    assert "account balance" in fc_res["snippets"][0]

    # 3. Execute agent consult
    async def mock_consult(q: str, tools: list[str] | None) -> str:
        return f"Consulted answer for {q} with {len(tools or [])} tools"

    res_consult = await execute_realtime_tool(
        tool_name="openclaw_agent_consult",
        arguments={"question": "Check project status"},
        session=session,
        tool_policy="safe-read-only",
        agent_consult_handler=mock_consult,
    )
    assert "Consulted answer for Check project status" in res_consult["answer"]


@pytest.mark.asyncio
async def test_runtime_session_scoping() -> None:
    cfg = VoiceCallConfig(
        enabled=True,
        provider="mock",
        session_scope="per-phone",
    )
    runtime = VoiceCallRuntime(cfg)

    # First initiate
    res1 = await runtime.initiate(to_number="+15555550123", message="First call")
    assert res1.is_ok
    call_id_1 = res1.unwrap().call_id

    # Second initiate to same phone in per-phone scope reuses session
    res2 = await runtime.initiate(to_number="+15555550123", message="Second call")
    assert res2.is_ok
    call_id_2 = res2.unwrap().call_id
    assert call_id_1 == call_id_2

    # Status check
    stat_res = await runtime.get_status(session_id=call_id_1)
    assert stat_res.is_ok
    data = stat_res.unwrap()
    assert data["active"] is True
    assert data["session"]["to"] == "+15555550123"


def test_tts_engine_overrides_and_formatting() -> None:
    engine = TTSEngine()
    global_cfg = VoiceCallConfig(
        tts=VoiceCallTTSConfig(
            provider="core",
            voice="standard",
            options={"rate": 1.0},
            providers={"openai": {"model": "tts-1", "speakerVoice": "alloy"}},
        )
    )

    # 1. Call-level ElevenLabs override deep merge
    override = VoiceCallTTSConfig(
        provider="elevenlabs",
        voice="Adam",
        options={"stability": 0.75},
        providers={"elevenlabs": {"modelId": "eleven_multilingual_v2"}},
    )
    effective = engine.resolve_effective_tts_config(override, global_cfg)

    assert effective.provider == "elevenlabs"
    assert effective.voice == "Adam"
    assert effective.options["rate"] == 1.0
    assert effective.options["stability"] == 0.75
    assert effective.providers["elevenlabs"]["modelId"] == "eleven_multilingual_v2"
    assert effective.providers["openai"]["model"] == "tts-1"

    # 2. Microsoft speech provider ignored for voice calls -> sanitized to core
    ms_override = VoiceCallTTSConfig(provider="microsoft", voice="Jenny")
    effective_ms = engine.resolve_effective_tts_config(ms_override, global_cfg)
    assert effective_ms.provider == "core"

    # 3. Text trimming
    long_text = "word " * 200
    trimmed = engine.prepare_spoken_text(long_text, max_chars=100)
    assert len(trimmed) <= 103
    assert trimmed.endswith("...")


@pytest.mark.asyncio
async def test_stream_disconnect_grace_and_reconnect() -> None:
    runtime = VoiceCallRuntime(VoiceCallConfig(disconnect_grace_seconds=0.1))
    session = CallSession(
        id="c_grace",
        provider="mock",
        from_number="+155501",
        to_number="+155502",
        direction="outbound",
        status="in-progress",
    )
    runtime._sessions["c_grace"] = session

    # Disconnect triggered -> grace timer starts
    runtime.handle_stream_disconnect("c_grace", grace_seconds=0.1)
    assert "c_grace" in runtime._disconnect_tasks

    # Reconnect immediately -> cancels timer, call stays active
    runtime.handle_stream_connect("c_grace")
    assert "c_grace" not in runtime._disconnect_tasks
    assert session.is_active is True


@pytest.mark.asyncio
async def test_speech_barge_in_clears_queue() -> None:
    runtime = VoiceCallRuntime()
    session = CallSession(
        id="c_barge",
        provider="mock",
        from_number="+155501",
        to_number="+155502",
        direction="inbound",
        status="in-progress",
    )
    runtime._sessions["c_barge"] = session

    # Queue an entry with an active future
    from extensions.voice_call.src.audio.tts_engine import QueuedPlaybackEntry

    fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
    entry = QueuedPlaybackEntry(id="p1", text="Unspoken previous reply", future=fut)
    runtime.tts_engine._pending_queues["c_barge"] = [entry]

    # Caller starts speaking -> barge-in clears queue and settles entry as skipped
    runtime.handle_caller_speech_start("c_barge")
    assert entry.status == "skipped"
    assert fut.done() is True
    assert fut.result() is False
    assert len(runtime.tts_engine._pending_queues.get("c_barge", [])) == 0


@pytest.mark.asyncio
async def test_realtime_and_streaming_audio_engines() -> None:
    rt_engine = RealtimeVoiceEngine()
    session = CallSession(
        id="c_rt",
        provider="mock",
        from_number="+155501",
        to_number="+155502",
        direction="outbound",
        agent_id="test-agent",
    )

    # Realtime start with Google Gemini defaults
    rt_cfg = VoiceCallRealtimeConfig(
        enabled=True,
        provider="google",
        providers={"google": {"speakerVoice": "Kore", "silenceDurationMs": 500}},
    )
    state = await rt_engine.start_session(session, rt_cfg, greeting="Hello realtime!")
    assert state.provider == "google"
    assert state.voice == "Kore"
    assert len(session.transcript) == 1
    assert session.transcript[0].text == "Hello realtime!"

    await rt_engine.record_user_speech(session, "How is the weather?")
    await rt_engine.record_agent_speech(session, "It is sunny.")
    assert len(session.transcript) == 3
    await rt_engine.end_session(session.id)

    # Streaming start with xAI defaults and queueing
    st_engine = StreamingTranscriptionEngine()
    st_cfg = VoiceCallStreamingConfig(
        enabled=True,
        provider="xai",
        providers={"xai": {"endpointingMs": 800, "encoding": "mulaw"}},
    )
    st_state = await st_engine.start_stream(session, st_cfg)
    assert st_state.provider == "xai"
    assert st_state.options["encoding"] == "mulaw"
    assert st_state.is_ready is False

    # Audio ingested while connecting is queued
    await st_engine.ingest_audio(session, b"\x00\x01\x02\x03")
    assert len(st_state.queued_audio_chunks) == 1

    # Mark ready drains queue
    queued = st_engine.mark_ready(session.id)
    assert len(queued) == 1
    assert st_engine.is_ready(session.id) is True

    turn = await st_engine.emit_transcript(session, "Transcribed utterance", is_final=True)
    assert turn.text == "Transcribed utterance"
    assert len(session.transcript) == 4
    await st_engine.end_stream(session.id)
