"""Tests for Google Meet URL normalization, regex matching, and target parsing."""

from extensions.google_meet.src.meet_url import (
    is_valid_google_meet_url,
    normalize_google_meet_url,
    parse_google_meet_target,
)
from extensions.google_meet.src.transports.google_meet_urls import (
    force_meet_english_ui,
    is_english_meet_tab,
    is_google_meet_page_url,
)


def test_is_valid_google_meet_url():
    assert is_valid_google_meet_url("https://meet.google.com/abc-defg-hij")
    assert is_valid_google_meet_url("https://meet.google.com/abc-defg-hij?authuser=1")
    assert is_valid_google_meet_url("http://meet.google.com/abc-defg-hij")
    assert is_valid_google_meet_url("https://meet.google.com/lookup/custom-code")
    assert not is_valid_google_meet_url("https://google.com")
    assert not is_valid_google_meet_url("https://meet.google.com/not-a-code")
    assert not is_valid_google_meet_url("invalid-url")


def test_normalize_google_meet_url():
    assert (
        normalize_google_meet_url("https://meet.google.com/abc-defg-hij?authuser=1")
        == "https://meet.google.com/abc-defg-hij"
    )
    assert (
        normalize_google_meet_url("http://meet.google.com/ABC-DEFG-HIJ")
        == "https://meet.google.com/abc-defg-hij"
    )


def test_parse_google_meet_target():
    # Space resource name
    t1 = parse_google_meet_target("spaces/abc-defg-hij")
    assert t1.is_valid
    assert t1.space_name == "spaces/abc-defg-hij"
    assert t1.meeting_code == "abc-defg-hij"
    assert t1.url == "https://meet.google.com/abc-defg-hij"

    # Full Meet URL
    t2 = parse_google_meet_target("https://meet.google.com/xyz-uvwx-rst")
    assert t2.is_valid
    assert t2.meeting_code == "xyz-uvwx-rst"
    assert t2.space_name == "spaces/xyz-uvwx-rst"
    assert t2.url == "https://meet.google.com/xyz-uvwx-rst"

    # Raw 10-letter meeting code with dashes
    t3 = parse_google_meet_target("xyz-uvwx-rst")
    assert t3.is_valid
    assert t3.meeting_code == "xyz-uvwx-rst"
    assert t3.url == "https://meet.google.com/xyz-uvwx-rst"

    # Invalid target
    t4 = parse_google_meet_target("random-string-not-meet")
    assert not t4.is_valid


def test_force_meet_english_ui():
    url = "https://meet.google.com/abc-defg-hij"
    english_url = force_meet_english_ui(url)
    assert "hl=en" in english_url
    assert force_meet_english_ui(english_url) == english_url


def test_is_english_meet_tab():
    assert is_english_meet_tab("https://meet.google.com/abc-defg-hij?hl=en")
    assert not is_english_meet_tab("https://meet.google.com/abc-defg-hij?hl=es")
    assert not is_english_meet_tab("https://meet.google.com/abc-defg-hij")


def test_is_google_meet_page_url():
    assert is_google_meet_page_url("https://meet.google.com/abc-defg-hij")
    assert is_google_meet_page_url("https://meet.google.com/landing")
    assert not is_google_meet_page_url("https://calendar.google.com")
