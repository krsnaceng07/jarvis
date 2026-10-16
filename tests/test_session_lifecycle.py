from datetime import datetime, timezone, timedelta
import pytest

from src.routing.session_lifecycle import is_session_expired
from src.sessions.session_store import SessionRecord

def _mock_record(
    created_iso: str,
    updated_iso: str,
    started_iso: str,
    last_iso: str
) -> SessionRecord:
    return SessionRecord(
        session_key="agent:main:main",
        agent_id="main",
        kind="direct",
        created_at=created_iso,
        updated_at=updated_iso,
        session_started_at=started_iso,
        last_interaction_at=last_iso,
        parent_session_key=None,
        thread_id=None,
        entries=tuple()
    )


def test_session_lifecycle_idle_mode(monkeypatch: pytest.MonkeyPatch):
    # Set current time to exactly 2026-08-13T12:00:00Z
    now = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)
    class MockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz:
                return now.astimezone(tz)
            return now
            
        @classmethod
        def fromisoformat(cls, date_string):
            return datetime.fromisoformat(date_string)

    
    monkeypatch.setattr("src.routing.session_lifecycle.datetime", MockDatetime)
    
    cfg = {
        "session": {
            "reset": {
                "mode": "idle",
                "idleMinutes": 30
            }
        }
    }
    
    # 29 minutes ago (not expired)
    last_iso = (now - timedelta(minutes=29)).isoformat().replace("+00:00", "Z")
    rec1 = _mock_record(last_iso, last_iso, last_iso, last_iso)
    assert not is_session_expired(rec1, cfg["session"], "")
    
    # 31 minutes ago (expired)
    last_iso2 = (now - timedelta(minutes=31)).isoformat().replace("+00:00", "Z")
    rec2 = _mock_record(last_iso2, last_iso2, last_iso2, last_iso2)
    assert is_session_expired(rec2, cfg["session"], "")


def test_session_lifecycle_daily_mode(monkeypatch: pytest.MonkeyPatch):
    # Current time is 12:00 local time
    now_local = datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
    now = now_local.astimezone(timezone.utc)

    class MockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz:
                return now.astimezone(tz)
            return now
            
        @classmethod
        def fromisoformat(cls, date_string):
            return datetime.fromisoformat(date_string)

            
    monkeypatch.setattr("src.routing.session_lifecycle.datetime", MockDatetime)
    
    cfg = {
        "session": {
            "reset": {
                "mode": "daily",
                "atHour": 4  # Rollover at 4 AM UTC
            }
        }
    }
    
    # Session started at 5 AM local time today (after 4 AM boundary) -> NOT EXPIRED
    started_local_1 = now_local.replace(hour=5)
    started_iso_1 = started_local_1.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    rec1 = _mock_record(started_iso_1, started_iso_1, started_iso_1, started_iso_1)
    assert not is_session_expired(rec1, cfg["session"], "")
    
    # Session started at 3 AM local time today (before 4 AM boundary) -> EXPIRED
    started_local_2 = now_local.replace(hour=3)
    started_iso_2 = started_local_2.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    rec2 = _mock_record(started_iso_2, started_iso_2, started_iso_2, started_iso_2)
    assert is_session_expired(rec2, cfg["session"], "")

    # Session started at 23 PM local time yesterday (before 4 AM boundary) -> EXPIRED
    started_local_3 = (now_local - timedelta(days=1)).replace(hour=23)
    started_iso_3 = started_local_3.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    rec3 = _mock_record(started_iso_3, started_iso_3, started_iso_3, started_iso_3)
    assert is_session_expired(rec3, cfg["session"], "")
