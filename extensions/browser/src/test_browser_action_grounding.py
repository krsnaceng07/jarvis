"""Regression coverage for target-preserving browser actions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from .browser_profiles import resolve_browser_config
from .browser_runtime import BrowserRuntime


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["Timeout: intercept", "strict mode violation", "not enabled"])
async def test_failed_click_never_chooses_another_target(reason):
    runtime = BrowserRuntime(resolve_browser_config({}))
    page = MagicMock(url="https://www.youtube.com/results?search_query=test")
    target = MagicMock()
    target.click = AsyncMock(side_effect=RuntimeError(reason))
    runtime.get_page = AsyncMock(return_value=page)
    runtime._resolve_element_locator = MagicMock(return_value=target)

    with pytest.raises(RuntimeError, match=reason):
        await runtime.act(kind="click", selector="#requested")

    target.click.assert_awaited_once()
    target.first.click.assert_not_called()
    target.dispatch_event.assert_not_called()
    page.locator.assert_not_called()
    page.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_wait_observes_target_readiness():
    runtime = BrowserRuntime(resolve_browser_config({}))
    page = MagicMock()
    page.title = AsyncMock(return_value="Ready")
    page.wait_for_load_state = AsyncMock()
    target = MagicMock()
    target.wait_for = AsyncMock()
    runtime.get_page = AsyncMock(return_value=page)
    runtime._resolve_element_locator = MagicMock(return_value=target)

    await runtime.act(kind="wait", selector="#search", timeout_ms=12000)
    target.wait_for.assert_awaited_once_with(state="visible", timeout=12000)
    page.wait_for_load_state.assert_not_awaited()

    runtime._resolve_element_locator.return_value = None
    await runtime.act(kind="wait", timeout_ms=12000)
    page.wait_for_load_state.assert_awaited_once_with("domcontentloaded", timeout=12000)
