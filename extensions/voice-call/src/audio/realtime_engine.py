"""Full-duplex realtime voice session coordinator (Gemini Live & OpenAI Realtime)."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine

from ..config import VoiceCallRealtimeConfig
from ..types import CallSession, CallTurn
from .agent_context import build_agent_voice_context_capsule
from .fast_context import search_fast_context
from .realtime_tools import (
    execute_realtime_tool,
    get_consult_policy_guidance,
    get_realtime_tools_definitions,
)

logger = logging.getLogger(__name__)

INACTIVITY_BACKSTOP_SECONDS = 30.0
INACTIVITY_GRACE_SECONDS = 2.0


@dataclass(slots=True)
class RealtimeSessionState:
    session_id: str
    provider: str
    model: str
    voice: str
    instructions: str
    tools: list[dict[str, Any]]
    turn_detection: dict[str, Any]
    started_at: float
    last_audio_in: float
    last_audio_out: float
    is_connected: bool = True
    inactivity_task: asyncio.Task[None] | None = None
    on_carrier_hangup: Callable[[], Coroutine[Any, Any, None]] | None = None
    custom_state: dict[str, Any] = field(default_factory=dict)


class RealtimeVoiceEngine:
    """Coordinates full-duplex realtime audio sessions, tools, and hangup detection."""

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace_root = Path(workspace_root) if workspace_root else Path.cwd()
        self._active_sessions: dict[str, RealtimeSessionState] = {}

    def build_voice_context(
        self,
        session: CallSession,
        config: VoiceCallRealtimeConfig,
    ) -> str:
        """Inject agent voice context, system instructions, consult policy, and caller background."""
        base_instructions = config.instructions or (
            "You are JARVIS, an AI assistant participating in a live telephony voice call. "
            "Speak naturally, clearly, and concisely. Keep responses short and conversational."
        )

        context_blocks = [base_instructions]

        # 1. Consult policy guidance
        consult_guidance = get_consult_policy_guidance(config.consult_policy)
        if consult_guidance:
            context_blocks.append(consult_guidance)

        # 2. Agent voice context capsule (SOUL.md, IDENTITY.md, USER.md, etc.)
        if config.agent_context.enabled:
            capsule = build_agent_voice_context_capsule(
                config.agent_context,
                workspace_root=self.workspace_root,
                agent_id=session.agent_id,
            )
            if capsule:
                context_blocks.append(capsule)

        # 3. Call metadata and recent conversation
        meta_lines = [
            f"Call Direction: {session.direction}",
            f"Caller: {session.from_number}",
            f"Recipient: {session.to_number}",
            f"Agent ID: {session.agent_id}",
        ]
        context_blocks.append("\n".join(meta_lines))

        if session.transcript:
            hist_lines = ["\nRecent conversation:"]
            for turn in session.transcript[-6:]:
                hist_lines.append(f"{turn.speaker.capitalize()}: {turn.text}")
            context_blocks.append("\n".join(hist_lines))

        return "\n\n".join(context_blocks)

    def resolve_provider_defaults(
        self,
        config: VoiceCallRealtimeConfig,
    ) -> tuple[str, str, str, dict[str, Any]]:
        """Resolve model, voice, and defaults for Gemini Live or OpenAI Realtime."""
        prov = config.provider.lower().strip()
        provider_cfg = config.providers.get(prov, {})

        if prov in ("google", "gemini"):
            resolved_prov = "google"
            model = config.model or provider_cfg.get("model") or "gemini-3.1-flash-live-preview"
            voice = (
                config.voice
                or provider_cfg.get("speakerVoice")
                or provider_cfg.get("voice")
                or "Kore"
            )
            turn_detection = config.turn_detection or {
                "silenceDurationMs": provider_cfg.get("silenceDurationMs", 500),
                "startSensitivity": provider_cfg.get("startSensitivity", "high"),
            }
        else:
            resolved_prov = "openai"
            model = config.model or provider_cfg.get("model") or "gpt-4o-realtime-preview"
            voice = config.voice or provider_cfg.get("voice") or "alloy"
            turn_detection = config.turn_detection or {
                "type": "server_vad",
                "silence_duration_ms": provider_cfg.get("silenceDurationMs", 500),
            }

        return resolved_prov, model, voice, turn_detection

    async def start_session(
        self,
        session: CallSession,
        config: VoiceCallRealtimeConfig,
        greeting: str | None = None,
        on_carrier_hangup: Callable[[], Coroutine[Any, Any, None]] | None = None,
    ) -> RealtimeSessionState:
        """Initialize a full-duplex realtime voice session."""
        instructions = self.build_voice_context(session, config)
        prov, model, voice, turn_detection = self.resolve_provider_defaults(config)
        tools = get_realtime_tools_definitions(
            tool_policy=config.tool_policy,
            custom_tools=config.tools,
        )

        now = time.time()
        state = RealtimeSessionState(
            session_id=session.id,
            provider=prov,
            model=model,
            voice=voice,
            instructions=instructions,
            tools=tools,
            turn_detection=turn_detection,
            started_at=now,
            last_audio_in=now,
            last_audio_out=now,
            is_connected=True,
            on_carrier_hangup=on_carrier_hangup,
        )

        # Start 30s inactivity backstop monitor
        state.inactivity_task = asyncio.create_task(
            self._monitor_inactivity(session.id, on_carrier_hangup)
        )
        self._active_sessions[session.id] = state

        if greeting:
            session.transcript.append(
                CallTurn(
                    speaker="agent",
                    text=greeting,
                    timestamp=now,
                )
            )

        return state

    async def _monitor_inactivity(
        self,
        session_id: str,
        on_carrier_hangup: Callable[[], Coroutine[Any, Any, None]] | None,
    ) -> None:
        """Monitor stream for 30s audio inactivity + 2s grace period backstop."""
        try:
            while True:
                await asyncio.sleep(5.0)
                state = self._active_sessions.get(session_id)
                if not state or not state.is_connected:
                    break

                now = time.time()
                inactive_duration = now - state.last_audio_in
                if inactive_duration >= INACTIVITY_BACKSTOP_SECONDS:
                    logger.info(
                        "Voice session %s: 30s inactivity detected, waiting 2s grace period...",
                        session_id,
                    )
                    await asyncio.sleep(INACTIVITY_GRACE_SECONDS)
                    # Recheck if audio resumed
                    state = self._active_sessions.get(session_id)
                    if state and (time.time() - state.last_audio_in >= INACTIVITY_BACKSTOP_SECONDS):
                        logger.warning(
                            "Voice session %s: inactivity backstop triggered. Ending carrier call.",
                            session_id,
                        )
                        await self.end_session(session_id, cause="inactivity_backstop")
                        break
        except asyncio.CancelledError:
            pass

    async def ingest_audio(self, session_id: str, audio_data: bytes) -> None:
        """Ingest incoming audio bytes and update activity timestamps."""
        state = self._active_sessions.get(session_id)
        if state:
            state.last_audio_in = time.time()

    async def handle_tool_call(
        self,
        session: CallSession,
        config: VoiceCallRealtimeConfig,
        tool_name: str,
        arguments: dict[str, Any],
        memory_provider: Any = None,
        agent_consult_handler: Callable[[str, list[str] | None], Coroutine[Any, Any, str]]
        | None = None,
    ) -> dict[str, Any]:
        """Handle tool calls from the realtime model with fastContext and consult policies."""
        state = self._active_sessions.get(session.id)
        on_end = state.on_carrier_hangup if state else None

        # Check fast context if tool is agent consult
        if (
            tool_name in ("openclaw_agent_consult", "jarvis_agent_consult")
            and config.fast_context.enabled
        ):
            question = str(arguments.get("question") or "")
            fc_result = await search_fast_context(
                query=question,
                session=session,
                timeout_ms=config.fast_context.timeout_ms,
                fallback_to_consult=config.fast_context.fallback_to_consult,
                memory_provider=memory_provider,
            )
            if fc_result.get("found") and not fc_result.get("fallbackToConsult"):
                snippets = "\n".join(fc_result.get("snippets", []))
                return {
                    "answer": f"Context snippet: {snippets}",
                    "question": question,
                    "source": "fastContext",
                }

        return await execute_realtime_tool(
            tool_name=tool_name,
            arguments=arguments,
            session=session,
            tool_policy=config.tool_policy,
            on_end_call=on_end,
            agent_consult_handler=agent_consult_handler,
        )

    async def record_user_speech(self, session: CallSession, text: str) -> None:
        """Record transcribed user utterance from realtime stream."""
        session.transcript.append(
            CallTurn(
                speaker="user",
                text=text,
                timestamp=time.time(),
            )
        )
        session.last_activity_time = time.time()

    async def record_agent_speech(self, session: CallSession, text: str) -> None:
        """Record agent spoken response from realtime model."""
        session.transcript.append(
            CallTurn(
                speaker="agent",
                text=text,
                timestamp=time.time(),
            )
        )
        session.last_activity_time = time.time()

    async def end_session(self, session_id: str, cause: str = "normal") -> None:
        """Close active realtime audio session and cascade teardown to carrier call."""
        state = self._active_sessions.pop(session_id, None)
        if state:
            state.is_connected = False
            if state.inactivity_task and not state.inactivity_task.done():
                state.inactivity_task.cancel()

            # Cascade close to carrier call so phone connection is not left open
            if state.on_carrier_hangup:
                try:
                    await state.on_carrier_hangup()
                except Exception as ex:
                    logger.error("Error cascading carrier hangup for %s: %s", session_id, ex)
