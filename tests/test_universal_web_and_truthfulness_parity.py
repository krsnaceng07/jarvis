"""tests.test_universal_web_and_truthfulness_parity — Universal Web automation and anti-hallucination verification.

Validates:
1. GenericWebAdapter on arbitrary websites (Wikipedia, GitHub, news, docs).
2. Resilient search input discovery and submission across diverse page layouts.
3. Cookie consent & GDPR banner auto-dismissal.
4. Text / article extraction without clutter.
5. ApplicationSessionManager universal routing (YouTube -> YouTubeAdapter, any other -> GenericWebAdapter).
6. ClaimGroundingFilter preventing model from speaking lies or hallucinating success for browser/media actions.
"""

from __future__ import annotations

import pytest

from src.agents.decision.truthfulness import ClaimGroundingFilter
from src.application_automation import (
    ActionEffect,
    ApplicationSessionManager,
)
from src.application_automation.applications.web import GenericWebAdapter
from src.application_automation.applications.youtube.adapter import YouTubeAdapter


class MockElement:
    def __init__(self, visible: bool = True, text: str = ""):
        self._visible = visible
        self._text = text
        self.clicked = False
        self.filled_value = None
        self.pressed_key = None

    async def is_visible(self) -> bool:
        return self._visible

    async def click(self) -> None:
        self.clicked = True

    async def fill(self, val: str) -> None:
        self.filled_value = val

    async def press(self, key: str) -> None:
        self.pressed_key = key


class MockLocator:
    def __init__(self, element: MockElement):
        self.element = element
        self.first = self

    async def click(self) -> None:
        await self.element.click()


class MockWebPage:
    def __init__(self, url: str = "https://en.wikipedia.org", title: str = "Wikipedia"):
        self.url = url
        self._title = title
        self.elements: dict[str, MockElement] = {}
        self.evaluated_scripts: list[str] = []
        self.eval_result = True
        self.goto_calls: list[str] = []

    async def title(self) -> str:
        return self._title

    async def query_selector(self, selector: str):
        return self.elements.get(selector)

    def locator(self, selector: str):
        el = self.elements.get(selector) or MockElement()
        return MockLocator(el)

    async def evaluate(self, script: str, *args):
        self.evaluated_scripts.append(script)
        if "article.innerText" in script or "document.body.innerText" in script:
            return "Nepal is a landlocked country in South Asia, situated mainly in the Himalayas."
        return self.eval_result

    async def goto(self, url: str, **kwargs):
        self.goto_calls.append(url)
        self.url = url


class TestUniversalWebAdapterParity:
    """Validates GenericWebAdapter on any website."""

    def test_can_handle_universal_web_urls(self) -> None:
        adapter = GenericWebAdapter()
        assert adapter.app_name == "web"
        assert adapter.can_handle("https://en.wikipedia.org/wiki/Nepal") is True
        assert adapter.can_handle("https://github.com/torvalds/linux") is True
        assert adapter.can_handle("https://news.ycombinator.com") is True
        assert adapter.can_handle("https://amazon.com/dp/B08N5WRWNW") is True
        assert adapter.can_handle("file:///C:/local/page.html") is False
        assert adapter.can_handle("", app_name="web") is True

    @pytest.mark.asyncio
    async def test_cookie_consent_auto_dismissal(self) -> None:
        adapter = GenericWebAdapter()
        page = MockWebPage("https://example.com")
        cookie_btn = MockElement(visible=True)
        page.elements['button:has-text("Accept all")'] = cookie_btn

        dismissed = await adapter.handle_interstitials(page)
        assert dismissed is True
        assert cookie_btn.clicked is True

    @pytest.mark.asyncio
    async def test_search_action_finds_input_and_submits(self) -> None:
        adapter = GenericWebAdapter()
        page = MockWebPage("https://en.wikipedia.org/wiki/Main_Page")
        search_input = MockElement(visible=True)
        page.elements['input[type="search"]'] = search_input

        res = await adapter.execute_action("search", {"query": "Quantum Computing"}, page)
        assert res.is_ok is True
        val = res.unwrap()
        assert val["action"] == "search"
        assert val["query"] == "Quantum Computing"
        assert search_input.clicked is True
        assert search_input.filled_value == "Quantum Computing"
        assert search_input.pressed_key == "Enter"
        assert adapter.get_current_state() == "SEARCH_RESULTS"

    @pytest.mark.asyncio
    async def test_search_fallback_to_site_search_url_when_input_not_found(self) -> None:
        adapter = GenericWebAdapter()
        page = MockWebPage("https://docs.python.org/3/")
        page.eval_result = False

        res = await adapter.execute_action("search", {"query": "asyncio"}, page)
        assert res.is_ok is True
        assert len(page.goto_calls) > 0
        assert "https://docs.python.org/search?q=asyncio" in page.goto_calls[0]

    @pytest.mark.asyncio
    async def test_read_action_extracts_page_text(self) -> None:
        adapter = GenericWebAdapter()
        page = MockWebPage("https://en.wikipedia.org/wiki/Nepal", title="Nepal - Wikipedia")

        res = await adapter.execute_action("read", {"maxChars": 500}, page)
        assert res.is_ok is True
        val = res.unwrap()
        assert val["action"] == "read"
        assert "Nepal is a landlocked country" in val["text"]
        assert val["title"] == "Nepal - Wikipedia"

    @pytest.mark.asyncio
    async def test_click_action_dispatches_to_locator(self) -> None:
        adapter = GenericWebAdapter()
        page = MockWebPage("https://github.com")

        res = await adapter.execute_action("click", {"selector": "a.nav-link"}, page)
        assert res.is_ok is True
        val = res.unwrap()
        assert val["action"] == "click"
        assert val["target"] == "a.nav-link"

    @pytest.mark.asyncio
    async def test_verify_action_truthfulness(self) -> None:
        adapter = GenericWebAdapter()
        page = MockWebPage("https://en.wikipedia.org/w/index.php?search=Nepal")

        verif = await adapter.verify_action("search", {"query": "Nepal"}, page)
        assert verif.effect == ActionEffect.CONFIRMED
        assert verif.verified is True


class TestApplicationSessionManagerUniversalRouting:
    """Validates session manager dispatch between YouTube and generic web."""

    def test_routing_youtube_url_to_youtube_adapter(self) -> None:
        mgr = ApplicationSessionManager()
        adapter = mgr.find_adapter_for_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert adapter is not None
        assert adapter.app_name == "youtube"
        assert isinstance(adapter, YouTubeAdapter)

    def test_routing_arbitrary_url_to_generic_web_adapter(self) -> None:
        mgr = ApplicationSessionManager()
        wiki = mgr.find_adapter_for_url("https://en.wikipedia.org/wiki/Artificial_intelligence")
        assert wiki is not None
        assert wiki.app_name == "web"
        assert isinstance(wiki, GenericWebAdapter)

        github = mgr.find_adapter_for_url("https://github.com/facebook/react")
        assert github is not None
        assert github.app_name == "web"


class TestTruthfulnessAndAntiHallucinationForBrowserActions:
    """Ensures JARVIS never speaks lies or claims success without tool proof."""

    def test_claiming_video_play_without_running_tool_is_intercepted(self) -> None:
        res = ClaimGroundingFilter.validate_and_ground(
            assistant_text="I have played Believer for you on YouTube.",
            recent_actions=[],
            last_execution_record=None,
        )
        assert res.is_truthful is False
        assert "have not executed that action yet" in res.grounded_text
        assert any("media_play" in d for d in res.discrepancies)

    def test_claiming_video_play_when_browser_tool_failed_is_corrected(self) -> None:
        res = ClaimGroundingFilter.validate_and_ground(
            assistant_text="I started playing the song for you.",
            recent_actions=[
                {
                    "tool": "browser",
                    "status": "failed",
                    "detail": "Video element not found on page",
                }
            ],
        )
        assert res.is_truthful is False
        assert "did not succeed" in res.grounded_text
        assert "Video element not found" in res.grounded_text

    def test_claiming_video_play_when_browser_tool_verified_is_truthfully_accepted(self) -> None:
        res = ClaimGroundingFilter.validate_and_ground(
            assistant_text="I have played Believer on YouTube for you.",
            recent_actions=[
                {
                    "tool": "browser",
                    "status": "success",
                    "detail": "Video playing, currentTime: 2.4s",
                }
            ],
        )
        assert res.is_truthful is True
        assert res.grounded_text == "I have played Believer on YouTube for you."

    def test_claiming_web_search_without_tool_is_intercepted(self) -> None:
        res = ClaimGroundingFilter.validate_and_ground(
            assistant_text="I have searched Google for Python documentation.",
            recent_actions=[],
        )
        assert res.is_truthful is False
        assert "have not executed that action yet" in res.grounded_text

    def test_claiming_web_search_with_unrelated_tool_is_intercepted(self) -> None:
        res = ClaimGroundingFilter.validate_and_ground(
            assistant_text="I have searched for latest tech news.",
            recent_actions=[{"tool": "mkdir", "status": "success", "target": "C:/tmp"}],
        )
        assert res.is_truthful is False
        assert "have not executed that action yet" in res.grounded_text

    def test_nepali_language_affirmative_browser_claims(self) -> None:
        res_no_tool = ClaimGroundingFilter.validate_and_ground(
            assistant_text="Hajur, maile Believer bajaidie.",
            recent_actions=[],
        )
        assert res_no_tool.is_truthful is False

        res_with_tool = ClaimGroundingFilter.validate_and_ground(
            assistant_text="Hajur, maile Believer bajaidie.",
            recent_actions=[{"tool": "browser", "status": "success"}],
        )
        assert res_with_tool.is_truthful is True
