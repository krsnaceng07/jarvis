"""tests.test_browser_tab_reuse_continuity — Test tab reuse, label affinity, and continuity.

Verifies:
1. Tab reuse by explicit label ('youtube') prevents duplicate tab creation.
2. Domain match on active watch page focuses without issuing destructive reload.
3. get_page resolves label alias ('youtube' -> target_id).
4. BrowserTool dispatches action='youtube' and action='app' to ApplicationSessionManager.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from extensions.browser.src.browser_runtime import BrowserRuntime, TabRecord
from extensions.browser.src.browser_tool import BrowserTool
from extensions.browser.src.config import ResolvedBrowserConfig
from src.application_automation import ApplicationSessionManager


from extensions.browser.src.browser_profiles import resolve_browser_config


def create_mock_config() -> ResolvedBrowserConfig:
    return resolve_browser_config({})


class TestBrowserTabReuseAndContinuityParity:
    """Verifies tab affinity, label resolution, and non-destructive tab reuse."""

    @pytest.mark.asyncio
    async def test_tab_reuse_by_label_prevents_duplicate_tabs(self) -> None:
        cfg = create_mock_config()
        runtime = BrowserRuntime(cfg)

        # Mock page and context
        mock_page = MagicMock()
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.url = "https://www.youtube.com"
        mock_page.title = AsyncMock(return_value="YouTube")
        mock_page.bring_to_front = AsyncMock()
        mock_page.goto = AsyncMock()

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        runtime.get_or_create_context = AsyncMock(return_value=mock_context)

        # Turn 1: Open YouTube with label="youtube"
        res1 = await runtime.open_tab(url="https://www.youtube.com", label="youtube")
        assert res1["ok"] is True
        assert res1["suggestedTargetId"] == "youtube"
        tab_id = res1["targetId"]
        assert len(runtime._tabs) == 1

        # Turn 2: User says "Open YouTube" again with label="youtube"
        res2 = await runtime.open_tab(url="https://www.youtube.com", label="youtube")
        assert res2["ok"] is True
        assert res2.get("reused") is True
        assert res2["targetId"] == tab_id
        assert res2["suggestedTargetId"] == "youtube"
        # Must NOT create a second tab!
        assert len(runtime._tabs) == 1
        mock_page.bring_to_front.assert_awaited()

    @pytest.mark.asyncio
    async def test_domain_reuse_on_watch_page_does_not_destructive_reload(self) -> None:
        cfg = create_mock_config()
        runtime = BrowserRuntime(cfg)

        # Tab currently on active watch page
        mock_page = MagicMock()
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.url = "https://www.youtube.com/watch?v=Believer"
        mock_page.title = AsyncMock(return_value="Imagine Dragons - Believer")
        mock_page.bring_to_front = AsyncMock()
        mock_page.goto = AsyncMock()

        rec = TabRecord(target_id="tab_1", page=mock_page, label="youtube")
        runtime._tabs["tab_1"] = rec
        runtime._active_tab_id = "tab_1"

        # Turn 2: User says "Go to YouTube" or model calls open_tab("https://www.youtube.com")
        res = await runtime.open_tab(url="https://www.youtube.com")
        assert res["ok"] is True
        assert res.get("reused") is True
        # Page should be focused
        mock_page.bring_to_front.assert_awaited_once()
        # Page should NOT be reloaded with goto("https://www.youtube.com"), which would kill video!
        mock_page.goto.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_page_resolves_label_alias(self) -> None:
        cfg = create_mock_config()
        runtime = BrowserRuntime(cfg)

        mock_page = MagicMock()
        mock_page.is_closed = MagicMock(return_value=False)
        rec = TabRecord(target_id="tab_99", page=mock_page, label="youtube")
        runtime._tabs["tab_99"] = rec

        mock_context = MagicMock()
        runtime.get_or_create_context = AsyncMock(return_value=mock_context)

        # Resolve via target_id="youtube" (label alias)
        page = await runtime.get_page(target_id="youtube")
        assert page == mock_page
        assert runtime._active_tab_id == "tab_99"

    @pytest.mark.asyncio
    async def test_browser_tool_action_youtube_dispatch(self) -> None:
        tool = BrowserTool()

        mock_page = MagicMock()
        mock_page.url = "https://www.youtube.com"

        with patch("extensions.browser.src.browser_tool.get_browser_runtime") as mock_get_rt:
            mock_rt = MagicMock()
            mock_rt.get_page = AsyncMock(return_value=mock_page)
            mock_get_rt.return_value = mock_rt

            with patch.object(ApplicationSessionManager.get_instance(), "execute_action") as mock_exec:
                from jarvis_sdk import Ok
                mock_exec.return_value = Ok({"action": "pause", "paused": True})

                res = await tool.execute(
                    "tc_1",
                    {
                        "action": "youtube",
                        "command": "pause",
                    },
                )
                assert res.details.get("ok") is True
                assert res.details.get("app") == "youtube"
                assert res.details.get("command") == "pause"
                mock_exec.assert_awaited_once()
