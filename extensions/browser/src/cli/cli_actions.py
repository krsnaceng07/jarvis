"""CLI commands for browser actions."""

import asyncio
from typing import Any

from ..browser_runtime import get_browser_runtime


def browser_navigate(args: Any) -> None:
    """Navigate current tab to target URL."""
    url = getattr(args, "url", "")

    async def _run() -> None:
        runtime = await get_browser_runtime()
        res = await runtime.navigate(url=url)
        print(f"Navigated to: {res.get('url')} (title: {res.get('title')})")

    asyncio.run(_run())


def browser_act(args: Any) -> None:
    """Execute interaction action on current tab."""
    action_kind = getattr(args, "action_kind", "")
    kwargs = vars(args).copy()
    kwargs.pop("func", None)
    kwargs.pop("action_kind", None)
    kwargs.pop("browser_command", None)
    kwargs.pop("browser_profile", None)

    async def _run() -> None:
        runtime = await get_browser_runtime()
        res = await runtime.act(kind=action_kind, **kwargs)
        print(f"Action '{action_kind}' executed: ok={res.get('ok')}")

    asyncio.run(_run())


def register_actions_cli(subparsers: Any) -> None:
    nav = subparsers.add_parser("navigate", help="Navigate to URL")
    nav.add_argument("url")
    nav.set_defaults(func=browser_navigate)

    # We will map all act kinds to browser_act for now
    actions = [
        ("resize", ["width", "height"]),
        ("click", ["ref", "--double"]),
        ("click-coords", ["x", "y"]),
        ("type", ["ref", "text", "--submit"]),
        ("press", ["key"]),
        ("hover", ["ref"]),
        ("scrollintoview", ["ref"]),
        ("drag", ["source_ref", "target_ref"]),
        ("select", ["ref", "options"]),  # Note: options should accept nargs='+'
        ("download", ["ref", "path"]),
        ("waitfordownload", ["path"]),
        ("upload", ["path", "--ref", "--input-ref", "--element"]),
        ("fill", ["--fields"]),
        ("dialog", ["--accept", "--dismiss", "--dialog-id"]),
        ("wait", ["selector", "--url", "--load", "--fn", "--text", "--timeout-ms"]),
        ("evaluate", ["--fn", "--ref", "--timeout-ms"]),
        ("highlight", ["ref"]),
        ("trace", ["state"]),
    ]

    for name, flags in actions:
        p = subparsers.add_parser(name, help=f"Execute {name} action")
        for f in flags:
            if f.startswith("--"):
                p.add_argument(f)
            else:
                if name == "select" and f == "options":
                    p.add_argument(f, nargs="+")
                else:
                    p.add_argument(f)
        p.set_defaults(func=browser_act, action_kind=name)
