"""Google Calendar API client for finding upcoming Meet links."""

from __future__ import annotations

import datetime
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any
import httpx

from jarvis_sdk import Err, Ok, Result

from .google_api_errors import google_api_error
from .meet_url import normalize_meet_url

GOOGLE_CALENDAR_API_BASE_URL = "https://www.googleapis.com/calendar/v3"
GOOGLE_CALENDAR_API_HOST = "www.googleapis.com"
GOOGLE_CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"
GOOGLE_CALENDAR_REQUEST_TIMEOUT_MS = 30000


def build_google_meet_calendar_day_window(
    now: datetime.datetime | None = None,
) -> tuple[str, str]:
    now_dt = now or datetime.datetime.now(datetime.timezone.utc)
    start_of_day = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = now_dt.replace(hour=23, minute=59, second=59, microsecond=999000)
    return start_of_day.isoformat(), end_of_day.isoformat()


@dataclass(slots=True)
class GoogleCalendarEventDate:
    date: str | None = None
    date_time: str | None = None
    time_zone: str | None = None


@dataclass(slots=True)
class GoogleCalendarConferenceEntryPoint:
    entry_point_type: str | None = None
    uri: str | None = None
    label: str | None = None


@dataclass(slots=True)
class GoogleMeetCalendarEvent:
    id: str | None = None
    summary: str | None = None
    description: str | None = None
    location: str | None = None
    status: str | None = None
    html_link: str | None = None
    hangout_link: str | None = None
    start: GoogleCalendarEventDate | None = None
    end: GoogleCalendarEventDate | None = None
    conference_data: dict[str, Any] | None = None


@dataclass(slots=True)
class GoogleMeetCalendarLookupResult:
    calendar_id: str
    event: GoogleMeetCalendarEvent
    meeting_uri: str


@dataclass(slots=True)
class GoogleMeetCalendarEventSelection:
    event: GoogleMeetCalendarEvent
    meeting_uri: str
    selected: bool = False


@dataclass(slots=True)
class GoogleMeetCalendarEventsResult:
    calendar_id: str
    events: list[GoogleMeetCalendarEventSelection] = field(default_factory=list)


def extract_google_meet_uri_from_calendar_event(
    event: GoogleMeetCalendarEvent,
) -> str | None:
    if event.hangout_link:
        try:
            return normalize_meet_url(event.hangout_link)
        except Exception:
            pass

    conference_data = event.conference_data or {}
    for ep in conference_data.get("entryPoints", []):
        if ep.get("entryPointType") == "video" and ep.get("uri"):
            try:
                return normalize_meet_url(ep["uri"])
            except Exception:
                pass

    candidates: list[str] = []
    if event.location:
        candidates.append(event.location)
    if event.description:
        candidates.append(event.description)

    for field_val in candidates:
        matches = re.finditer(
            r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}", field_val, re.IGNORECASE
        )
        for m in matches:
            try:
                return normalize_meet_url(m.group(0))
            except Exception:
                pass

    return None


def parse_calendar_event_date(value: Any) -> GoogleCalendarEventDate | None:
    if not isinstance(value, dict):
        return None
    return GoogleCalendarEventDate(
        date=value.get("date"),
        date_time=value.get("dateTime"),
        time_zone=value.get("timeZone"),
    )


def parse_calendar_event(value: dict[str, Any]) -> GoogleMeetCalendarEvent:
    return GoogleMeetCalendarEvent(
        id=value.get("id"),
        summary=value.get("summary"),
        description=value.get("description"),
        location=value.get("location"),
        status=value.get("status"),
        html_link=value.get("htmlLink"),
        hangout_link=value.get("hangoutLink"),
        start=parse_calendar_event_date(value.get("start")),
        end=parse_calendar_event_date(value.get("end")),
        conference_data=value.get("conferenceData"),
    )


def parse_event_start_epoch_ms(event: GoogleMeetCalendarEvent) -> float | None:
    dt_str = event.start.date_time if event.start else None
    if not dt_str:
        return None
    try:
        dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.timestamp() * 1000.0
    except Exception:
        return None


def choose_best_meet_calendar_event(
    events: list[GoogleMeetCalendarEvent],
    now: datetime.datetime,
) -> GoogleMeetCalendarEvent | None:
    now_ms = now.timestamp() * 1000.0
    with_meet = [e for e in events if extract_google_meet_uri_from_calendar_event(e) is not None]
    if not with_meet:
        return None

    def distance(e: GoogleMeetCalendarEvent) -> float:
        start_ms = parse_event_start_epoch_ms(e)
        if start_ms is None:
            return float("inf")
        return abs(start_ms - now_ms)

    return min(with_meet, key=distance)


async def fetch_google_calendar_events(
    *,
    access_token: str,
    calendar_id: str | None = None,
    event_query: str | None = None,
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 50,
    now: datetime.datetime | None = None,
) -> tuple[str, list[GoogleMeetCalendarEvent], datetime.datetime]:
    cal_id = calendar_id.strip() if calendar_id and calendar_id.strip() else "primary"
    encoded_id = urllib.parse.quote(cal_id, safe="")
    url = f"{GOOGLE_CALENDAR_API_BASE_URL}/calendars/{encoded_id}/events"

    now_dt = now or datetime.datetime.now(datetime.timezone.utc)
    params: dict[str, str] = {
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": str(max(1, min(max_results, 250))),
        "conferenceDataVersion": "1",
    }
    if event_query and event_query.strip():
        params["q"] = event_query.strip()
    if time_min and time_min.strip():
        params["timeMin"] = time_min.strip()
    else:
        params["timeMin"] = (now_dt - datetime.timedelta(hours=2)).isoformat()
    if time_max and time_max.strip():
        params["timeMax"] = time_max.strip()

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=GOOGLE_CALENDAR_REQUEST_TIMEOUT_MS / 1000.0) as client:
        response = await client.get(url, headers=headers, params=params)
        if response.status_code >= 400:
            raise await google_api_error(
                response=response,
                prefix="Google Calendar events.list",
                scopes=[GOOGLE_CALENDAR_EVENTS_SCOPE],
            )
        payload = response.json()
        raw_items = payload.get("items", [])
        if not isinstance(raw_items, list):
            raise ValueError("Google Calendar events.list response had non-array items")
        events = [parse_calendar_event(i) for i in raw_items if isinstance(i, dict)]
        return cal_id, events, now_dt


async def list_google_meet_calendar_events(
    *,
    access_token: str,
    calendar_id: str | None = None,
    event_query: str | None = None,
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 50,
    now: datetime.datetime | None = None,
) -> GoogleMeetCalendarEventsResult:
    cal_id, events, now_dt = await fetch_google_calendar_events(
        access_token=access_token,
        calendar_id=calendar_id,
        event_query=event_query,
        time_min=time_min,
        time_max=time_max,
        max_results=max_results,
        now=now,
    )
    best = choose_best_meet_calendar_event(events, now_dt)
    selections: list[GoogleMeetCalendarEventSelection] = []
    for event in events:
        meeting_uri = extract_google_meet_uri_from_calendar_event(event)
        if meeting_uri:
            selections.append(
                GoogleMeetCalendarEventSelection(
                    event=event,
                    meeting_uri=meeting_uri,
                    selected=(event == best),
                )
            )
    return GoogleMeetCalendarEventsResult(calendar_id=cal_id, events=selections)


async def find_google_meet_calendar_event(
    *,
    access_token: str,
    calendar_id: str | None = None,
    event_query: str | None = None,
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 50,
    now: datetime.datetime | None = None,
) -> GoogleMeetCalendarLookupResult:
    result = await list_google_meet_calendar_events(
        access_token=access_token,
        calendar_id=calendar_id,
        event_query=event_query,
        time_min=time_min,
        time_max=time_max,
        max_results=max_results,
        now=now,
    )
    selected = next((e for e in result.events if e.selected), None)
    if not selected and result.events:
        selected = result.events[0]
    if not selected:
        raise RuntimeError("No Google Calendar event with a Google Meet link matched the query")
    return GoogleMeetCalendarLookupResult(
        calendar_id=result.calendar_id,
        event=selected.event,
        meeting_uri=selected.meeting_uri,
    )


async def list_upcoming_calendar_events_with_meet(
    *,
    token: str,
    limit: int = 10,
    time_min: str | None = None,
    time_max: str | None = None,
    calendar_id: str | None = None,
) -> Result[list[dict[str, Any]], str]:
    """List upcoming calendar events that have Google Meet video calls."""
    try:
        res = await list_google_meet_calendar_events(
            access_token=token,
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            max_results=limit,
        )
        events_list = []
        for s in res.events:
            event_dict = vars(s.event)
            event_dict["meetingUri"] = s.meeting_uri
            event_dict["selected"] = s.selected
            events_list.append(event_dict)
        return Ok(events_list)
    except Exception as e:
        return Err(str(e))
