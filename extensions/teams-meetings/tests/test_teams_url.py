"""Tests for Teams Meetings URL validation, categorization, and normalization."""

from __future__ import annotations

import pytest

from extensions.teams_meetings.src.teams_url import (
    is_consumer_teams_url,
    is_work_teams_url,
    normalize_teams_url,
)
from extensions.teams_meetings.src.transports.teams_urls import (
    is_recoverable_teams_tab,
    is_same_teams_url_for_reuse,
    normalize_teams_url_for_reuse,
)


def test_work_teams_url_validation() -> None:
    work_url = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_NzQx...%40thread.v2/0?context=%7b%22Tid%22%3a%22...%22%7d"
    assert is_work_teams_url(work_url) is True
    assert is_consumer_teams_url(work_url) is False
    normalized = normalize_teams_url(work_url)
    assert normalized.startswith("https://teams.microsoft.com/l/meetup-join/")

    work_cloud_url = "https://teams.cloud.microsoft/l/meetup-join/19%3ameeting_xyz%40thread.v2/0"
    assert is_work_teams_url(work_cloud_url) is True
    assert normalize_teams_url(work_cloud_url).startswith(
        "https://teams.cloud.microsoft/l/meetup-join/"
    )


def test_consumer_teams_url_validation() -> None:
    consumer_url = "https://teams.live.com/meet/948329482934?p=AbCdEfGh"
    assert is_consumer_teams_url(consumer_url) is True
    assert is_work_teams_url(consumer_url) is False
    normalized = normalize_teams_url(consumer_url)
    assert normalized.startswith("https://teams.live.com/meet/948329482934")


def test_invalid_teams_urls_raise() -> None:
    # Empty
    with pytest.raises(ValueError, match="Teams meeting URL is required"):
        normalize_teams_url("")

    # Non-Teams host
    with pytest.raises(ValueError, match="Unsupported Teams meeting host"):
        normalize_teams_url("https://zoom.us/j/123456789")

    with pytest.raises(ValueError, match="Unsupported Teams meeting host"):
        normalize_teams_url("https://meet.google.com/abc-defg-hij")

    # Invalid path for work
    with pytest.raises(ValueError, match="Invalid Teams work meeting URL path"):
        normalize_teams_url("https://teams.microsoft.com/dashboard/home")

    # Invalid path for consumer
    with pytest.raises(ValueError, match="Invalid Teams consumer meeting URL path"):
        normalize_teams_url("https://teams.live.com/settings")


def test_teams_url_reuse_and_recovery() -> None:
    url1 = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_123%40thread.v2/0?context=abc"
    url2 = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_123%40thread.v2/0?context=xyz"
    url3 = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_456%40thread.v2/0"

    assert is_same_teams_url_for_reuse(url1, url2) is True
    assert is_same_teams_url_for_reuse(url1, url3) is False

    norm_reuse = normalize_teams_url_for_reuse(url1)
    assert norm_reuse == "https://teams.microsoft.com/l/meetup-join/19%3ameeting_123%40thread.v2/0"

    tab = {"url": url1, "title": "Microsoft Teams"}
    assert is_recoverable_teams_tab(tab, url2) is True
    assert is_recoverable_teams_tab(tab, url3) is False
