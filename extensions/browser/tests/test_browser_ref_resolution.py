"""Tests for browser element ref resolution (e1, e2) and timeout bounding."""

from unittest.mock import MagicMock
from extensions.browser.src.browser_runtime import (
    _resolve_element_locator,
    _ACT_DEFAULT_TIMEOUT_MS,
)


def test_default_interaction_timeout_is_bounded():
    """Verify default interaction timeout is 8000ms (matching OpenClaw act-policy.ts)."""
    assert _ACT_DEFAULT_TIMEOUT_MS == 8000


def test_resolve_element_locator_with_selector():
    """When a standard CSS selector is provided, locator uses that selector."""
    page = MagicMock()
    page.url = "https://example.com"

    _resolve_element_locator(page, selector="#custom-id", ref=None)
    page.locator.assert_called_with("#custom-id")


def test_resolve_element_locator_ref_e1_on_youtube():
    """When ref='e1' on YouTube, resolves to first video title / thumbnail locator."""
    page = MagicMock()
    page.url = "https://www.youtube.com/results?search_query=tere+naam"
    loc_mock = MagicMock()
    page.locator.return_value = loc_mock

    _resolve_element_locator(page, selector=None, ref="e1")
    assert page.locator.called
    loc_mock.nth.assert_called_with(0)


def test_resolve_element_locator_ref_e3_on_youtube():
    """When ref='e3' on YouTube, resolves to 3rd video (index 2)."""
    page = MagicMock()
    page.url = "https://www.youtube.com/watch?v=abc"
    loc_mock = MagicMock()
    page.locator.return_value = loc_mock

    _resolve_element_locator(page, selector=None, ref="e3")
    assert page.locator.called
    loc_mock.nth.assert_called_with(2)


def test_resolve_element_locator_ref_e1_on_google():
    """When ref='e1' on Google Search, resolves to first search result title."""
    page = MagicMock()
    page.url = "https://www.google.com/search?q=openclaw"
    loc_mock = MagicMock()
    page.locator.return_value = loc_mock

    _resolve_element_locator(page, selector=None, ref="e1")
    assert page.locator.called
    loc_mock.nth.assert_called_with(0)


def test_resolve_element_locator_ref_e1_on_generic_domain():
    """When ref='e1' on generic page, resolves to role/aria or first visible interactive element."""
    page = MagicMock()
    page.url = "https://docs.openclaw.ai"
    loc_mock = MagicMock()
    page.locator.return_value = loc_mock

    _resolve_element_locator(page, selector=None, ref="e1")
    assert page.locator.called
