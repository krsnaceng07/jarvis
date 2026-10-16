"""Playwright automation actions for the Browser tool."""

from playwright.async_api import Page
from .browser_tool_schema import BrowserActSchema


async def perform_act(page: Page, request: BrowserActSchema) -> str:
    """Execute a single browser action on the given page with fast auto-wait and strict-mode resilience."""
    if request.ref:
        selector = f"[data-ref='{request.ref}']" if request.ref.isdigit() else request.ref
    elif request.selector:
        selector = request.selector
    else:
        selector = "body"

    # Smart candidate fallback for search boxes (e.g. YouTube input#search)
    candidates = [selector]
    if "input#search" in selector or (
        request.kind in ("type", "fill") and "search" in selector.lower()
    ):
        candidates = [
            "input[name='search_query']",
            "input#search",
            "input.yt-searchbox-input",
            "#search input",
            "input[type='text']",
            selector,
        ]

    locator = None
    for cand in candidates:
        try:
            cand_loc = page.locator(cand).first
            if await cand_loc.count() > 0:
                locator = cand_loc
                break
        except Exception:
            continue

    if locator is None:
        base_locator = page.locator(selector)
        locator = base_locator.first if hasattr(base_locator, "first") else base_locator

    kind = request.kind

    # Fast 3000ms wait for element readiness
    if kind in ("click", "type", "press", "hover", "scrollIntoView", "fill"):
        try:
            await locator.wait_for(state="attached", timeout=3000)
        except Exception:
            pass

    if kind == "click":
        if request.doubleClick:
            await locator.dblclick(timeout=5000)
        else:
            await locator.click(timeout=5000)
        return "Clicked successfully."

    elif kind in ("type", "fill"):
        if request.text is not None:
            await locator.fill(request.text, timeout=5000)
            if request.submit:
                await locator.press("Enter", timeout=5000)
            return f"Typed '{request.text}' successfully."
        return "No text provided to type."

    elif kind == "press":
        if request.key:
            await locator.press(request.key, timeout=5000)
            return f"Pressed '{request.key}' successfully."
        return "No key provided to press."

    elif kind == "hover":
        await locator.hover(timeout=5000)
        return "Hovered successfully."

    elif kind == "scrollIntoView":
        await locator.scroll_into_view_if_needed(timeout=5000)
        return "Scrolled into view successfully."

    elif kind == "wait":
        if request.timeMs:
            await page.wait_for_timeout(request.timeMs)
            return f"Waited {request.timeMs}ms."
        return "Waited."

    return f"Action '{kind}' executed."
