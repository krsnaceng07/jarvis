"""CLI commands for browser inspection."""

import asyncio
from pathlib import Path
from typing import Any

from ..browser_runtime import get_browser_runtime


def browser_screenshot(args: Any) -> None:
    """Take a screenshot of current tab or element."""
    full_page = bool(getattr(args, "full_page", False))
    ref = getattr(args, "ref", None)

    async def _run() -> None:
        runtime = await get_browser_runtime()
        out_path = "E:/jarvis/.temp/screenshot.png"
        res = await runtime.screenshot(full_page=full_page, selector=ref, path=out_path)
        print(f"Screenshot captured: {res.get('path')} (size: {len(res.get('base64', ''))} chars)")

    asyncio.run(_run())


def browser_snapshot(args: Any) -> None:
    """Take a DOM ARIA snapshot of current tab."""
    fmt = getattr(args, "format", "aria")
    limit = getattr(args, "limit", None)
    out = getattr(args, "out", None)

    async def _run() -> None:
        runtime = await get_browser_runtime()
        res = await runtime.snapshot(snapshot_format=fmt, max_chars=limit)
        text = res.get("snapshot", "")
        if out:
            Path(out).write_text(text, encoding="utf-8")
            print(f"Snapshot saved to: {out} ({len(text)} chars)")
        else:
            print(text)

    asyncio.run(_run())


def browser_console(args: Any) -> None:
    """View console messages from current tab."""

    async def _run() -> None:
        runtime = await get_browser_runtime()
        res = await runtime.get_console()
        messages = res.get("messages", [])
        if not messages:
            print("No console logs captured.")
            return
        print(f"Console Logs ({len(messages)}):")
        for m in messages:
            print(f"  {m}")

    asyncio.run(_run())


def browser_errors(args: Any) -> None:
    """View uncaught page errors from current tab."""

    async def _run() -> None:
        runtime = await get_browser_runtime()
        res = await runtime.get_errors()
        errors = res.get("errors", [])
        if not errors:
            print("No page errors captured.")
            return
        print(f"Page Errors ({len(errors)}):")
        for e in errors:
            print(f"  {e}")

    asyncio.run(_run())


def browser_requests(args: Any) -> None:
    print("Network requests monitoring: no active requests recorded.")


def browser_pdf(args: Any) -> None:
    print("PDF export is not supported in current headless profile.")


def browser_responsebody(args: Any) -> None:
    print("Response body inspection: not recorded.")


def register_inspection_cli(subparsers: Any) -> None:
    screenshot = subparsers.add_parser("screenshot", help="Take a screenshot")
    screenshot.add_argument("--full-page", action="store_true")
    screenshot.add_argument("--ref")
    screenshot.add_argument("--labels", action="store_true")
    screenshot.set_defaults(func=browser_screenshot)

    snapshot = subparsers.add_parser("snapshot", help="Take a DOM snapshot")
    snapshot.add_argument("--format", default="ai")
    snapshot.add_argument("--limit", type=int)
    snapshot.add_argument("--interactive", action="store_true")
    snapshot.add_argument("--compact", action="store_true")
    snapshot.add_argument("--depth", type=int)
    snapshot.add_argument("--efficient", action="store_true")
    snapshot.add_argument("--labels", action="store_true")
    snapshot.add_argument("--urls", action="store_true")
    snapshot.add_argument("--selector")
    snapshot.add_argument("--frame")
    snapshot.add_argument("--out")
    snapshot.set_defaults(func=browser_snapshot)

    console = subparsers.add_parser("console", help="View console logs")
    console.add_argument("--level")
    console.set_defaults(func=browser_console)

    errors = subparsers.add_parser("errors", help="View errors")
    errors.add_argument("--clear", action="store_true")
    errors.set_defaults(func=browser_errors)

    reqs = subparsers.add_parser("requests", help="View requests")
    reqs.add_argument("--filter")
    reqs.add_argument("--clear", action="store_true")
    reqs.set_defaults(func=browser_requests)

    pdf = subparsers.add_parser("pdf", help="Generate PDF")
    pdf.set_defaults(func=browser_pdf)

    resp = subparsers.add_parser("responsebody", help="Get response body")
    resp.add_argument("pattern")
    resp.add_argument("--max-chars", type=int)
    resp.set_defaults(func=browser_responsebody)
