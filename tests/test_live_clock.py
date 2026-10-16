"""tests.test_live_clock — Unit tests for LiveClock and temporal prompt context."""

from src.system.live_clock import LiveClock


def test_live_clock_datetime():
    data = LiveClock.get_current_datetime()
    assert isinstance(data, dict)
    assert data["timestamp"] > 0
    assert len(data["datetime_iso"]) > 0
    assert data["year"] >= 2024
    assert 1 <= data["month"] <= 12
    assert 1 <= data["day"] <= 31
    assert data["weekday"] in (
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
    )
    assert len(data["timezone"]) > 0
    assert data["utc_offset"].startswith(("+", "-"))
    assert data["verified"] is True


def test_live_clock_formatting():
    formatted_12 = LiveClock.get_current_time(use_24h=False)
    assert "AM" in formatted_12 or "PM" in formatted_12

    formatted_24 = LiveClock.get_current_time(use_24h=True)
    assert ":" in formatted_24

    current_date = LiveClock.get_current_date()
    assert len(current_date) == 10
    assert current_date.count("-") == 2


def test_build_temporal_context_prompt():
    prompt = LiveClock.build_temporal_context_prompt()
    assert "Temporal Context" in prompt
    assert "Current date:" in prompt
    assert "Current time:" in prompt
    assert "Time zone:" in prompt
    assert "Rule:" in prompt
