"""Host seam for the bundled browser tool.

The Playwright/Selenium browser tool is owned by ``extensions/browser``. Core
code and other extensions must not import sibling extension internals
(``tools.ci.check_imports``), so everything that needs the browser goes through
this one module instead.

Contract: accessors return ``None`` when the browser extension is absent or
fails to import. Callers treat ``None`` as "browser capability unavailable" and
fall back to whatever surface they own — never as a hard error, because the
host must still start on installs that ship without the extension.
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger("jarvis.tools.browser_host")


def get_browser_tool() -> Any | None:
    """Return a fresh browser tool instance, or ``None`` when unavailable."""
    try:
        from extensions.browser.src.browser_tool import BrowserTool
    except Exception as exc:  # noqa: BLE001 - optional bundled extension
        _log.debug("browser tool unavailable: %s", exc)
        return None

    try:
        return BrowserTool()
    except Exception as exc:  # noqa: BLE001 - constructor must not break callers
        _log.warning("browser tool construction failed: %s", exc)
        return None


def browser_tool_entry() -> dict[str, Any] | None:
    """Return the browser tool as a host tool-entry dict, or ``None``.

    Shaped like the entries produced by
    ``src.agents.sessions.tools.create_coding_tools`` so it can be appended to
    the same list without a second adapter.
    """
    tool = get_browser_tool()
    if tool is None:
        return None
    return {
        "name": "browser",
        "description": tool.description,
        "parameters": tool.parameters,
        "execute": lambda call_id, args: tool.execute(call_id, args),
        "call": lambda action, args: tool.call(action, args),
    }


__all__ = ["browser_tool_entry", "get_browser_tool"]
