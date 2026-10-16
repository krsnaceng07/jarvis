"""CLI commands for browser tabs."""

import asyncio
from typing import Any

from ..browser_runtime import get_browser_runtime


def browser_tabs(args: Any) -> None:
    """List open browser tabs."""

    async def _run() -> None:
        runtime = await get_browser_runtime()
        tabs = await runtime.list_tabs()
        if not tabs:
            print("No open tabs.")
            return

        print("Open Tabs:")
        for t in tabs:
            active_mark = "*" if t.get("active") else " "
            label_part = f" ({t.get('label')})" if t.get("label") else ""
            print(
                f" {active_mark} [{t.get('targetId')}] {t.get('title', 'Untitled')} - {t.get('url', 'about:blank')}{label_part}"
            )

    asyncio.run(_run())


def browser_tab(args: Any) -> None:
    """Perform a tab subcommand action (new, select, close, label)."""
    sub = getattr(args, "tab_command", None)

    async def _run() -> None:
        runtime = await get_browser_runtime()
        if sub == "new":
            tab = await runtime.open_tab(url="about:blank", label=getattr(args, "label", "") or "")
            print(f"Created tab [{tab.get('targetId')}]")
        elif sub == "select":
            target_id = getattr(args, "id", "")
            focused = await runtime.focus_tab(target_id=target_id)
            if focused.get("ok"):
                print(f"Selected tab [{target_id}]")
            else:
                print(f"Failed to select tab [{target_id}]")
        elif sub == "close":
            target_id = getattr(args, "id", "")
            closed = await runtime.close_tab(target_id=target_id)
            if closed.get("ok"):
                print(f"Closed tab [{target_id}]")
            else:
                print(f"Failed to close tab [{target_id}]")
        elif sub == "label":
            target_id = getattr(args, "id", "")
            label = getattr(args, "label", "")
            if target_id in runtime._tabs:
                runtime._tabs[target_id].label = label
                print(f"Labeled tab [{target_id}]: '{label}'")
            else:
                print(f"Tab [{target_id}] not found")
        else:
            tabs = await runtime.list_tabs()
            print(f"Active tabs count: {len(tabs)}")

    asyncio.run(_run())


def browser_open(args: Any) -> None:
    """Open a URL in a new tab."""
    url = getattr(args, "url", "about:blank")

    async def _run() -> None:
        runtime = await get_browser_runtime()
        tab = await runtime.open_tab(url=url)
        print(f"Opened tab [{tab.get('targetId')}]: {tab.get('url')}")

    asyncio.run(_run())


def browser_focus(args: Any) -> None:
    """Focus a tab by target ID."""
    tab_id = getattr(args, "id", "")

    async def _run() -> None:
        runtime = await get_browser_runtime()
        res = await runtime.focus_tab(target_id=tab_id)
        if res.get("ok"):
            print(f"Focused tab [{tab_id}]: {res.get('url')}")
        else:
            print(f"Tab [{tab_id}] not found")

    asyncio.run(_run())


def browser_close(args: Any) -> None:
    """Close a tab by target ID."""
    tab_id = getattr(args, "id", "")

    async def _run() -> None:
        runtime = await get_browser_runtime()
        res = await runtime.close_tab(target_id=tab_id)
        if res.get("ok"):
            print(f"Closed tab [{tab_id}]")
        else:
            print(f"Tab [{tab_id}] not found or already closed")

    asyncio.run(_run())


def register_tabs_cli(subparsers: Any) -> None:
    tabs_parser = subparsers.add_parser("tabs", help="List tabs")
    tabs_parser.set_defaults(func=browser_tabs)

    tab_parser = subparsers.add_parser("tab", help="Tab operations")
    tab_subs = tab_parser.add_subparsers(dest="tab_command")

    tab_new = tab_subs.add_parser("new")
    tab_new.add_argument("--label")
    tab_new.set_defaults(func=browser_tab)

    tab_label = tab_subs.add_parser("label")
    tab_label.add_argument("id")
    tab_label.add_argument("label")
    tab_label.set_defaults(func=browser_tab)

    tab_select = tab_subs.add_parser("select")
    tab_select.add_argument("id")
    tab_select.set_defaults(func=browser_tab)

    tab_close = tab_subs.add_parser("close")
    tab_close.add_argument("id")
    tab_close.set_defaults(func=browser_tab)

    tab_parser.set_defaults(func=browser_tab)

    open_parser = subparsers.add_parser("open", help="Open a URL")
    open_parser.add_argument("url")
    open_parser.set_defaults(func=browser_open)

    focus_parser = subparsers.add_parser("focus", help="Focus a tab")
    focus_parser.add_argument("id")
    focus_parser.set_defaults(func=browser_focus)

    close_parser = subparsers.add_parser("close", help="Close a tab")
    close_parser.add_argument("id")
    close_parser.set_defaults(func=browser_close)
