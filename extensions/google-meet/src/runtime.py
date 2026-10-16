"""Google Meet runtime managing active meeting sessions, transports, and lifecycles."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from .config import GoogleMeetConfig
from .runtime_probes import (
    test_google_meet_listening,
    test_google_meet_speech,
)
from .runtime_session import (
    is_browser_transport,
    note_session,
    resolve_mode,
    resolve_transport,
    with_session_agent_config,
)
from .runtime_setup import get_google_meet_runtime_setup_status
from .transports.chrome import (
    launch_chrome_meet,
    launch_chrome_meet_on_node,
    leave_chrome_meet,
    read_chrome_meet_transcript,
    recover_current_meet_tab,
)
from .transports.google_meet_platform_adapter import (
    GOOGLE_MEET_PLATFORM_ADAPTER,
    is_talk_back_mode,
)
from .transports.types import (
    GoogleMeetChromeSession,
    GoogleMeetJoinRequest,
    GoogleMeetJoinResult,
    GoogleMeetSession,
    GoogleMeetTranscriptSnapshot,
    GoogleMeetTwilioSession,
)
from .voice_call_gateway import (
    create_voice_call_gateway,
    end_meet_voice_call_gateway_call,
    get_meet_voice_call_gateway_call,
    join_meet_via_voice_call_gateway,
    speak_meet_via_voice_call_gateway,
)


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class GoogleMeetRuntime:
    def __init__(
        self,
        *,
        config: GoogleMeetConfig | dict[str, Any] | None = None,
        full_config: Any = None,
        runtime: Any = None,
        logger: Any = None,
    ) -> None:
        if isinstance(config, GoogleMeetConfig):
            self.config = config
        elif isinstance(config, dict):
            from .config import resolve_google_meet_config

            res = resolve_google_meet_config(config)
            self.config = res.unwrap() if res.is_ok else GoogleMeetConfig()
        else:
            self.config = GoogleMeetConfig()
        self.full_config = full_config
        self.runtime = runtime
        self.logger = logger
        self._created_browser_tabs: dict[str, str] = {}
        self._sessions: dict[str, GoogleMeetSession] = {}
        self._voice_call_gateway = create_voice_call_gateway(
            {"config": self.config.voice_call, "runtime": runtime}
        )

    def update_config(self, config: GoogleMeetConfig | dict[str, Any]) -> None:
        if isinstance(config, GoogleMeetConfig):
            self.config = config
        elif isinstance(config, dict):
            from .config import resolve_google_meet_config

            res = resolve_google_meet_config(config)
            self.config = res.unwrap() if res.is_ok else GoogleMeetConfig()

    def list(self) -> list[GoogleMeetSession]:
        return list(self._sessions.values())

    async def status(
        self, session_id: str | None = None
    ) -> list[GoogleMeetSession] | GoogleMeetSession | None:
        if session_id:
            session = self._sessions.get(session_id)
            if session:
                await self._refresh_status(session)
            return session
        for s in self._sessions.values():
            await self._refresh_status(s)
        return list(self._sessions.values())

    async def get_status(self, session_id: str | None = None) -> dict[str, Any]:
        stat = await self.status(session_id)
        if session_id:
            return {
                "active": stat.state == "active" if isinstance(stat, GoogleMeetSession) else False,
                "session": stat,
            }
        sessions = stat if isinstance(stat, list) else []
        active_session = next((s for s in sessions if s.state == "active"), None)
        return {
            "active": active_session is not None,
            "session": active_session,
            "sessions": sessions,
        }

    async def transcript(
        self, session_id: str, options: dict[str, Any] | None = None
    ) -> GoogleMeetTranscriptSnapshot | None:
        session = self._sessions.get(session_id)
        if not session:
            return None
        return await self._capture_transcript(session, options or {})

    async def get_transcript(
        self, session_id: str | None = None, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        target_id = session_id
        if not target_id:
            active = next((s for s in self._sessions.values() if s.state == "active"), None)
            target_id = active.id if active else None
        if not target_id:
            return {"transcript": [], "count": 0}
        snap = await self.transcript(target_id, options)
        lines = [
            line.__dict__ if hasattr(line, "__dict__") else line
            for line in (snap.lines if snap else [])
        ]
        return {"transcript": lines, "count": len(lines), "snapshot": snap}

    def transcript_source_runtime(self) -> Any:
        return self

    async def setup_status(self, options: dict[str, Any] | None = None) -> Any:
        return await get_google_meet_runtime_setup_status(
            config=self.config,
            full_config=self.full_config,
            runtime=self.runtime,
            options=options,
        )

    async def create_via_browser(self) -> Any:
        result = await GOOGLE_MEET_PLATFORM_ADAPTER.create.browser(
            runtime=self.runtime,
            config=self.config,
        )
        if result.opened_by_plugin and result.target_id:
            self._created_browser_tabs[f"{result.node_id}:{result.target_id}"] = result.meeting_uri
        return result

    async def recover_current_tab(self, request: dict[str, Any] | None = None) -> dict[str, Any]:
        req = request or {}
        transport = resolve_transport(req.get("transport"), self.config)
        if transport == "twilio":
            raise ValueError("recover_current_tab only supports chrome or chrome-node transports")
        url = (
            GOOGLE_MEET_PLATFORM_ADAPTER.urls.validate_and_normalize(req["url"])
            if req.get("url")
            else None
        )
        return await recover_current_meet_tab(
            runtime=self.runtime,
            config=self.config,
            full_config=self.full_config,
            transport=transport,
            url=url,
        )

    async def recover_tab(self, request: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.recover_current_tab(request)

    async def join(
        self,
        request: GoogleMeetJoinRequest | None = None,
        *,
        url: str | None = None,
        target: str | None = None,
        mode: str | None = None,
        transport: str | None = None,
        agent_id: str | None = None,
        audio_in: str | None = None,
        audio_out: str | None = None,
        profile: str | None = None,
        node: str | None = None,
        dial_in_number: str | None = None,
        pin: str | None = None,
        dtmf_sequence: str | None = None,
        message: str | None = None,
        requester_session_key: str | None = None,
        **kwargs: Any,
    ) -> GoogleMeetJoinResult:
        if request is None:
            request = GoogleMeetJoinRequest(
                url=url or target or "",
                mode=mode,
                transport=transport,
                agent_id=agent_id,
                audio_in=audio_in,
                audio_out=audio_out,
                profile=profile,
                node=node,
                dial_in_number=dial_in_number,
                pin=pin,
                dtmf_sequence=dtmf_sequence,
                message=message,
                requester_session_key=requester_session_key,
            )
        normalized_url = GOOGLE_MEET_PLATFORM_ADAPTER.urls.validate_and_normalize(request.url)
        transport = resolve_transport(request.transport, self.config)
        mode = resolve_mode(request.mode, self.config)
        agent_id = request.agent_id or self.config.realtime.agent_id or "default"

        # Check reusable active session
        for existing in self._sessions.values():
            if (
                existing.state == "active"
                and existing.transport == transport
                and GOOGLE_MEET_PLATFORM_ADAPTER.urls.is_same_meeting(existing.url, normalized_url)
            ):
                note_session(existing, "Reused existing active Meet session.")
                return GoogleMeetJoinResult(
                    session=existing,
                    reused=True,
                    spoken=False,
                )

        session_id = f"meet_{uuid.uuid4().hex[:12]}"
        session = GoogleMeetSession(
            id=session_id,
            url=normalized_url,
            transport=transport,
            mode=mode,
            agent_id=agent_id,
            state="active",
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        self._sessions[session_id] = session

        spoken = False
        if is_browser_transport(transport):
            chrome_config = with_session_agent_config(self.config, agent_id)
            launch_fn = (
                launch_chrome_meet_on_node if transport == "chrome-node" else launch_chrome_meet
            )
            launch_res = await launch_fn(
                runtime=self.runtime,
                config=chrome_config,
                full_config=self.full_config,
                meeting_session_id=session_id,
                requester_session_key=request.requester_session_key,
                mode=mode,
                url=normalized_url,
                logger=self.logger,
            )
            node_id = launch_res.get("node_id")
            tab = launch_res.get("tab")
            session.chrome = GoogleMeetChromeSession(
                audio_backend=launch_res.get("audio_backend"),
                launched=launch_res.get("launched", False),
                node_id=node_id,
                browser_profile=self.config.chrome.browser_profile,
                browser_tab=tab,
                health=launch_res.get("browser"),
            )
            session.notes.append(
                "Chrome transport joins as the signed-in Google profile and routes realtime audio through the configured bridge."
                if is_talk_back_mode(mode)
                else "Chrome transport joins as the signed-in Google profile without starting the realtime audio bridge."
            )
        elif transport == "twilio":
            dial_plan = GOOGLE_MEET_PLATFORM_ADAPTER.dial_in.build_plan(
                dial_in_number=request.dial_in_number,
                default_dial_in_number=self.config.twilio.default_dial_in_number,
                pin=request.pin,
                default_pin=self.config.twilio.default_pin,
                dtmf_sequence=request.dtmf_sequence,
                default_dtmf_sequence=self.config.twilio.default_dtmf_sequence,
                dtmf_delay_ms=self.config.voice_call.dtmf_delay_ms,
            )
            dial_in_number = dial_plan.get("number")
            if not dial_in_number:
                raise ValueError(
                    "Twilio transport requires a Meet dial-in phone number. Google Meet URLs do not include dial-in details; pass dialInNumber with optional pin/dtmfSequence, configure twilio.defaultDialInNumber, or use chrome/chrome-node transport."
                )
            dtmf_sequence = dial_plan.get("dtmfSequence")
            vc_res = (
                await join_meet_via_voice_call_gateway(
                    config=self.config,
                    gateway=self._voice_call_gateway,
                    dial_in_number=dial_in_number,
                    dtmf_sequence=dtmf_sequence,
                    logger=self.logger,
                    requester_session_key=request.requester_session_key,
                    agent_id=agent_id,
                    session_key=f"voice:google-meet:{session_id}",
                    message=request.message
                    or self.config.voice_call.intro_message
                    or self.config.realtime.intro_message
                    if is_talk_back_mode(mode)
                    else None,
                )
                if self.config.voice_call.enabled
                else None
            )
            session.twilio = GoogleMeetTwilioSession(
                dial_in_number=dial_in_number,
                pin_provided=bool(dial_plan.get("pin")),
                dtmf_sequence=dtmf_sequence,
                voice_call_id=vc_res.get("call_id") if vc_res else None,
                dtmf_sent=vc_res.get("dtmf_sent") if vc_res else None,
                intro_sent=vc_res.get("intro_sent") if vc_res else None,
            )
            spoken = bool(vc_res and vc_res.get("intro_sent"))

        session.updated_at = now_iso()
        return GoogleMeetJoinResult(session=session, reused=False, spoken=spoken)

    async def leave(
        self, session_id: str | None = None, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if session_id:
            session = self._sessions.get(session_id)
            if not session:
                return {"left": False, "note": "Meeting session not found"}
            left = await self._release_browser_tab(session)
            if session.transport == "twilio" and session.twilio and session.twilio.voice_call_id:
                await end_meet_voice_call_gateway_call(
                    gateway=self._voice_call_gateway,
                    call_id=session.twilio.voice_call_id,
                )
            session.state = "ended"
            session.ended_at = now_iso()
            session.updated_at = now_iso()
            return {"left": left if left is not None else True, "session": session}

        active_sessions = [s for s in self._sessions.values() if s.state == "active"]
        for s in active_sessions:
            await self._release_browser_tab(s)
            if s.transport == "twilio" and s.twilio and s.twilio.voice_call_id:
                await end_meet_voice_call_gateway_call(
                    gateway=self._voice_call_gateway,
                    call_id=s.twilio.voice_call_id,
                )
            s.state = "ended"
            s.ended_at = now_iso()
            s.updated_at = now_iso()
        return {"left": True, "count": len(active_sessions)}

    async def speak(
        self,
        session_id: str | None = None,
        instructions: str | None = None,
        *,
        text: str | None = None,
    ) -> dict[str, Any]:
        target_session = (
            self._sessions.get(session_id)
            if session_id
            else next((s for s in self._sessions.values() if s.state == "active"), None)
        )
        if not target_session and session_id:
            raise ValueError("Meeting session not found")
        msg = text or instructions or ""
        if (
            target_session
            and target_session.transport == "twilio"
            and target_session.twilio
            and target_session.twilio.voice_call_id
        ):
            out_msg = (
                msg
                or self.config.voice_call.intro_message
                or self.config.realtime.intro_message
                or ""
            )
            await speak_meet_via_voice_call_gateway(
                gateway=self._voice_call_gateway,
                call_id=target_session.twilio.voice_call_id,
                message=out_msg,
            )
            target_session.twilio.intro_sent = True
            target_session.updated_at = now_iso()
            return {"handled": True, "spoken": True, "text": out_msg}
        return {"handled": True, "spoken": True, "text": msg}

    async def test_speech(self, request: GoogleMeetJoinRequest) -> dict[str, Any]:
        return await test_google_meet_speech(self, request)

    async def test_listen(self, request: GoogleMeetJoinRequest) -> dict[str, Any]:
        return await test_google_meet_listening(self, request)

    def resolve_agent_id(self, request: GoogleMeetJoinRequest) -> str:
        return request.agent_id or self.config.realtime.agent_id or "default"

    def is_reusable(self, session: GoogleMeetSession, resolved: dict[str, Any]) -> bool:
        return (
            session.state == "active"
            and session.transport == resolved.get("transport")
            and GOOGLE_MEET_PLATFORM_ADAPTER.urls.is_same_meeting(session.url, resolved.get("url"))
        )

    def has_health_handle(self, session_id: str) -> bool:
        return session_id in self._sessions

    def refresh_health(self, session_id: str) -> None:
        pass

    async def refresh_caption_health(self, session: GoogleMeetSession) -> None:
        if (
            is_browser_transport(session.transport)
            and session.chrome
            and session.chrome.browser_tab
        ):
            try:
                snap = await read_chrome_meet_transcript(
                    runtime=self.runtime,
                    config=self.config,
                    meeting_url=session.url,
                    meeting_session_id=session.id,
                    tab=session.chrome.browser_tab,
                    transport=session.transport,
                    node_id=session.chrome.node_id,
                )
                if session.chrome.health:
                    session.chrome.health.transcript_lines = len(snap.lines)
                    if snap.lines:
                        last_line = snap.lines[-1]
                        session.chrome.health.last_caption_text = last_line.text
                        session.chrome.health.last_caption_speaker = last_line.speaker
                        session.chrome.health.last_caption_at = last_line.at
            except Exception:
                pass

    async def _refresh_status(self, session: GoogleMeetSession) -> None:
        if is_browser_transport(session.transport):
            if session.chrome and session.chrome.browser_tab:
                try:
                    res = await recover_current_meet_tab(
                        runtime=self.runtime,
                        config=self.config,
                        full_config=self.full_config,
                        transport=session.transport,
                        mode=session.mode,
                        read_only=True,
                        tracked_meeting_url=session.url,
                        tracked_target_id=session.chrome.browser_tab.target_id,
                        url=session.url,
                    )
                    if res.get("found") and res.get("browser"):
                        session.chrome.health = res["browser"]
                except Exception:
                    pass
        elif session.transport == "twilio" and session.twilio and session.twilio.voice_call_id:
            try:
                call_stat = await get_meet_voice_call_gateway_call(
                    gateway=self._voice_call_gateway,
                    call_id=session.twilio.voice_call_id,
                )
                if not call_stat.get("found"):
                    session.state = "ended"
                    session.ended_at = now_iso()
            except Exception:
                pass

    async def _capture_transcript(
        self, session: GoogleMeetSession, options: dict[str, Any]
    ) -> GoogleMeetTranscriptSnapshot | None:
        tab = session.chrome.browser_tab if session.chrome else None
        if not tab:
            return None
        return await read_chrome_meet_transcript(
            runtime=self.runtime,
            config=self.config,
            meeting_url=session.url,
            meeting_session_id=session.id,
            tab=tab,
            transport=session.transport,
            node_id=session.chrome.node_id if session.chrome else None,
            finalize=options.get("finalize", False),
        )

    async def _release_browser_tab(self, session: GoogleMeetSession) -> bool | None:
        if not is_browser_transport(session.transport):
            return None
        tab = session.chrome.browser_tab if session.chrome else None
        if not tab:
            note_session(
                session,
                "No tracked Meet browser tab for this session; close the Meet tab manually if it is still in the call.",
            )
            session.browser_left = False
            return False

        shared = any(
            other.id != session.id
            and other.state == "active"
            and is_browser_transport(other.transport)
            and other.chrome
            and other.chrome.browser_tab
            and other.chrome.browser_tab.target_id == tab.target_id
            for other in self._sessions.values()
        )
        if shared:
            note_session(
                session,
                "Kept the shared Meet tab open because another active session uses it.",
            )
            session.browser_left = None
            return None

        try:
            result = await leave_chrome_meet(
                runtime=self.runtime,
                config=self.config,
                meeting_session_id=session.id,
                meeting_url=session.url,
                tab=tab,
                transport=session.transport,
                node_id=session.chrome.node_id if session.chrome else None,
            )
            note_session(session, result.get("note", ""))
            left = result.get("left", False)
        except Exception as error:
            note_session(session, f"Browser control could not leave the Meet tab: {error}")
            left = False

        if session.chrome and left:
            session.chrome.browser_tab = None
        session.browser_left = left
        return left
