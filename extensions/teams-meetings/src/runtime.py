"""Teams Meetings runtime managing active meeting sessions, transports, and lifecycles."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from jarvis_sdk import Err, Ok, Result

from .config import TeamsMeetingsConfig, resolve_teams_meetings_config
from .runtime_probes import (
    test_teams_meetings_listening,
    test_teams_meetings_speech,
)
from .runtime_session import (
    is_browser_transport,
    note_session,
    resolve_mode,
    resolve_transport,
    with_session_agent_config,
)
from .runtime_setup import validate_teams_meetings_runtime_setup
from .transports.chrome import (
    launch_chrome_teams,
    launch_chrome_teams_on_node,
    leave_chrome_teams,
    read_chrome_teams_transcript,
    recover_current_teams_tab,
)
from .transports.teams_platform_adapter import (
    TEAMS_MEETINGS_PLATFORM_ADAPTER,
    is_talk_back_mode,
)
from .transports.types import (
    TeamsMeetingsChromeSession,
    TeamsMeetingsJoinRequest,
    TeamsMeetingsSession,
    TeamsMeetingsTranscriptSnapshot,
)


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class TeamsMeetingsRuntime:
    def __init__(
        self,
        *,
        config: TeamsMeetingsConfig | dict[str, Any] | None = None,
        full_config: Any = None,
        runtime: Any = None,
        logger: Any = None,
    ) -> None:
        if isinstance(config, TeamsMeetingsConfig):
            self.config = config
        elif isinstance(config, dict):
            res = resolve_teams_meetings_config(config)
            self.config = res.unwrap() if res.is_ok else TeamsMeetingsConfig()
        else:
            self.config = TeamsMeetingsConfig()
        self.full_config = full_config
        self.runtime = runtime
        self.logger = logger
        self._created_browser_tabs: dict[str, str] = {}
        self._sessions: dict[str, TeamsMeetingsSession] = {}

    def update_config(self, config: TeamsMeetingsConfig | dict[str, Any]) -> None:
        if isinstance(config, TeamsMeetingsConfig):
            self.config = config
        elif isinstance(config, dict):
            res = resolve_teams_meetings_config(config)
            self.config = res.unwrap() if res.is_ok else TeamsMeetingsConfig()

    def list(self) -> list[TeamsMeetingsSession]:
        return list(self._sessions.values())

    async def status(
        self, session_id: str | None = None
    ) -> list[TeamsMeetingsSession] | TeamsMeetingsSession | None:
        if session_id:
            session = self._sessions.get(session_id)
            if session:
                await self._refresh_status(session)
            return session
        for s in self._sessions.values():
            await self._refresh_status(s)
        return list(self._sessions.values())

    async def get_status(self, session_id: str | None = None) -> Result[dict[str, Any], str]:
        stat = await self.status(session_id)
        if session_id:
            return Ok(
                {
                    "active": stat.state == "active"
                    if isinstance(stat, TeamsMeetingsSession)
                    else False,
                    "session": stat,
                }
            )
        sessions = stat if isinstance(stat, list) else []
        active_session = next((s for s in sessions if s.state == "active"), None)
        return Ok(
            {
                "active": active_session is not None,
                "session": active_session,
                "sessions": sessions,
            }
        )

    async def transcript(
        self, session_id: str, options: dict[str, Any] | None = None
    ) -> TeamsMeetingsTranscriptSnapshot | None:
        session = self._sessions.get(session_id)
        if not session:
            return None
        return await self._capture_transcript(session, options or {})

    async def get_transcript(
        self, session_id: str | None = None, limit: int = 50, options: dict[str, Any] | None = None
    ) -> Result[list[dict[str, Any]], str]:
        target_id = session_id
        if not target_id:
            active = next((s for s in self._sessions.values() if s.state == "active"), None)
            target_id = active.id if active else None
        if not target_id:
            return Ok([])
        snap = await self.transcript(target_id, options)
        lines = [
            {
                "speaker": line.speaker,
                "text": line.text,
                "at": line.at,
            }
            for line in (snap.lines if snap else [])
        ]
        return Ok(lines[:limit])

    async def setup_status(self, options: dict[str, Any] | None = None) -> Any:
        opts = options or {}
        return await validate_teams_meetings_runtime_setup(
            config=self.config,
            node_id=opts.get("node"),
            transport=opts.get("transport"),
            mode=opts.get("mode"),
        )

    async def recover_current_tab(self, request: dict[str, Any] | None = None) -> dict[str, Any]:
        req = request or {}
        transport = resolve_transport(req.get("transport"), self.config)
        url = (
            TEAMS_MEETINGS_PLATFORM_ADAPTER.urls.validate_and_normalize(req["url"])
            if req.get("url") or req.get("target_url")
            else None
        )
        return await recover_current_teams_tab(
            runtime=self.runtime,
            config=self.config,
            full_config=self.full_config,
            transport=transport,
            url=url,
        )

    async def recover_tab(
        self,
        request: dict[str, Any] | None = None,
        target_url: str | None = None,
        browser_profile: str | None = None,
        node_id: str | None = None,
        transport: str | None = None,
        **kwargs: Any,
    ) -> Result[dict[str, Any], str]:
        req = dict(request) if isinstance(request, dict) else {}
        if target_url:
            req["url"] = target_url
        if browser_profile:
            req["profile"] = browser_profile
        if node_id:
            req["node"] = node_id
        if transport:
            req["transport"] = transport
        req.update(kwargs)
        res = await self.recover_current_tab(req)
        return Ok(res)

    async def join(
        self,
        request: TeamsMeetingsJoinRequest | None = None,
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
        message: str | None = None,
        requester_session_key: str | None = None,
        **kwargs: Any,
    ) -> Result[dict[str, Any], str]:
        if request is None:
            request = TeamsMeetingsJoinRequest(
                url=url or target or "",
                mode=mode,
                transport=transport,
                agent_id=agent_id,
                audio_in=audio_in,
                audio_out=audio_out,
                profile=profile,
                node=node,
                message=message,
                requester_session_key=requester_session_key,
            )
        try:
            normalized_url = TEAMS_MEETINGS_PLATFORM_ADAPTER.urls.validate_and_normalize(
                request.url
            )
        except Exception as err:
            return Err(str(err))

        transport_str = resolve_transport(request.transport, self.config)
        mode_str = resolve_mode(request.mode, self.config)
        agent_id_str = request.agent_id or self.config.realtime.agent_id or "default"

        # Check reusable active session
        for existing in self._sessions.values():
            if (
                existing.state == "active"
                and existing.transport == transport_str
                and TEAMS_MEETINGS_PLATFORM_ADAPTER.urls.is_same_meeting(
                    existing.url, normalized_url
                )
            ):
                note_session(existing, "Reused existing active Teams session.")
                return Ok(
                    {
                        "session": existing,
                        "reused": True,
                        "spoken": False,
                    }
                )

        session_id = f"teams_{uuid.uuid4().hex[:12]}"
        session = TeamsMeetingsSession(
            id=session_id,
            url=normalized_url,
            transport=transport_str,
            mode=mode_str,
            agent_id=agent_id_str,
            state="active",
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        self._sessions[session_id] = session

        chrome_config = with_session_agent_config(self.config, agent_id_str)
        launch_fn = (
            launch_chrome_teams_on_node if transport_str == "chrome-node" else launch_chrome_teams
        )
        launch_res = await launch_fn(
            runtime=self.runtime,
            config=chrome_config,
            full_config=self.full_config,
            meeting_session_id=session_id,
            requester_session_key=request.requester_session_key,
            mode=mode_str,
            url=normalized_url,
            logger=self.logger,
        )
        node_id = launch_res.get("node_id")
        tab = launch_res.get("tab")
        session.chrome = TeamsMeetingsChromeSession(
            audio_backend=launch_res.get("audio_backend"),
            launched=launch_res.get("launched", False),
            node_id=node_id,
            browser_profile=self.config.chrome.browser_profile,
            browser_tab=tab,
            health=launch_res.get("browser"),
        )
        session.notes.append(
            "Chrome transport joins Teams as guest and routes realtime audio through the configured bridge."
            if is_talk_back_mode(mode_str)
            else "Chrome transport joins Teams as guest without starting the realtime audio bridge."
        )

        session.updated_at = now_iso()
        return Ok(
            {
                "session": session,
                "reused": False,
                "spoken": False,
            }
        )

    async def leave(
        self, session_id: str | None = None, options: dict[str, Any] | None = None
    ) -> Result[dict[str, Any], str]:
        if session_id:
            session = self._sessions.get(session_id)
            if not session:
                return Err("Meeting session not found")
            left = await self._release_browser_tab(session)
            session.state = "ended"
            session.ended_at = now_iso()
            session.updated_at = now_iso()
            return Ok({"left": left if left is not None else True, "session": session})

        active_sessions = [s for s in self._sessions.values() if s.state == "active"]
        for s in active_sessions:
            await self._release_browser_tab(s)
            s.state = "ended"
            s.ended_at = now_iso()
            s.updated_at = now_iso()
        return Ok({"left": True, "count": len(active_sessions)})

    async def speak(
        self,
        text: str | None = None,
        session_id: str | None = None,
        instructions: str | None = None,
    ) -> Result[dict[str, Any], str]:
        target_session = (
            self._sessions.get(session_id)
            if session_id
            else next((s for s in self._sessions.values() if s.state == "active"), None)
        )
        if not target_session and session_id:
            return Err("Meeting session not found")
        msg = text or instructions or ""
        return Ok({"handled": True, "spoken": True, "text": msg})

    async def test_speech(self, request: TeamsMeetingsJoinRequest) -> dict[str, Any]:
        return await test_teams_meetings_speech(self, request)

    async def test_listen(self, request: TeamsMeetingsJoinRequest) -> dict[str, Any]:
        return await test_teams_meetings_listening(self, request)

    def resolve_agent_id(self, request: TeamsMeetingsJoinRequest) -> str:
        return request.agent_id or self.config.realtime.agent_id or "default"

    async def refresh_caption_health(self, session: TeamsMeetingsSession) -> None:
        if (
            is_browser_transport(session.transport)
            and session.chrome
            and session.chrome.browser_tab
        ):
            try:
                snap = await read_chrome_teams_transcript(
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

    async def _refresh_status(self, session: TeamsMeetingsSession) -> None:
        if is_browser_transport(session.transport):
            if session.chrome and session.chrome.browser_tab:
                try:
                    res = await recover_current_teams_tab(
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

    async def _capture_transcript(
        self, session: TeamsMeetingsSession, options: dict[str, Any]
    ) -> TeamsMeetingsTranscriptSnapshot | None:
        tab = session.chrome.browser_tab if session.chrome else None
        if not tab:
            return None
        return await read_chrome_teams_transcript(
            runtime=self.runtime,
            config=self.config,
            meeting_url=session.url,
            meeting_session_id=session.id,
            tab=tab,
            transport=session.transport,
            node_id=session.chrome.node_id if session.chrome else None,
            finalize=options.get("finalize", False),
        )

    async def _release_browser_tab(self, session: TeamsMeetingsSession) -> bool | None:
        if not is_browser_transport(session.transport):
            return None
        tab = session.chrome.browser_tab if session.chrome else None
        if not tab:
            session.browser_left = False
            return False

        try:
            result = await leave_chrome_teams(
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
            note_session(session, f"Browser control could not leave the Teams tab: {error}")
            left = False

        if session.chrome and left:
            session.chrome.browser_tab = None
        session.browser_left = left
        return left
