import asyncio
from pathlib import Path
import shutil
import sys
from typing import Any

from ..browser_runtime import get_browser_runtime


def browser_doctor(args: Any) -> None:
    """Check browser profile availability and dependencies."""

    async def _run() -> None:
        runtime = await get_browser_runtime()
        report = await runtime.doctor()

        print("Browser Doctor:")
        for check in report.get("checks", []):
            status = "[OK]" if check.get("ok") else "[FAIL]"
            print(f"  {status} {check.get('name')}: {check.get('detail', '')}")

        if report.get("ok"):
            print("\nAll browser checks passed successfully.")
        else:
            print("\nSome browser doctor checks failed. See details above.", file=sys.stderr)

    asyncio.run(_run())


def browser_start(args: Any) -> None:
    """Start the browser runtime."""
    headless = getattr(args, "headless", True)

    async def _run() -> None:
        runtime = await get_browser_runtime()
        print("Starting browser runtime...")
        await runtime.ensure_browser(headless=headless)
        status = runtime.get_status()
        print(f"Browser running with profile '{status.get('profile')}'.")

    asyncio.run(_run())


def browser_stop(args: Any) -> None:
    """Stop the browser runtime."""

    async def _run() -> None:
        runtime = await get_browser_runtime()
        await runtime.stop()
        print("Browser runtime stopped.")

    asyncio.run(_run())


def browser_status(args: Any) -> None:
    """Print status of browser runtime."""

    async def _run() -> None:
        runtime = await get_browser_runtime()
        status = runtime.get_status()
        running_str = "Running" if status.get("running") else "Stopped"
        print(f"Browser Status: {running_str}")
        print(f"  Profile: {status.get('profile')}")
        print(f"  Open Tabs: {status.get('tabs_count')}")
        print(f"  Active Tab: {status.get('active_tab_id', 'None')}")

    asyncio.run(_run())


def browser_reset_profile(args: Any) -> None:
    """Reset the browser profile user data directory."""

    async def _run() -> None:
        runtime = await get_browser_runtime()
        await runtime.stop()
        profile_dir = Path("E:/jarvis/.temp/browser") / runtime.resolved.defaultProfile
        if profile_dir.exists():
            shutil.rmtree(profile_dir, ignore_errors=True)
            print(f"Reset browser profile directory: {profile_dir}")
        else:
            print(f"Profile directory already clean: {profile_dir}")

    asyncio.run(_run())


def register_lifecycle_cli(subparsers: Any) -> None:
    doc_parser = subparsers.add_parser(
        "doctor", help="Check browser profile availability and dependencies."
    )
    doc_parser.add_argument("--deep", action="store_true", help="Add a live snapshot probe")
    doc_parser.set_defaults(func=browser_doctor)

    start_parser = subparsers.add_parser(
        "start", help="Start the background browser control service."
    )
    start_parser.add_argument(
        "--headless", action="store_true", help="One-shot local managed headless launch"
    )
    start_parser.set_defaults(func=browser_start)

    stop_parser = subparsers.add_parser("stop", help="Stop the background browser control service.")
    stop_parser.set_defaults(func=browser_stop)

    status_parser = subparsers.add_parser("status", help="Get status")
    status_parser.set_defaults(func=browser_status)

    reset_parser = subparsers.add_parser(
        "reset-profile", help="Moves the profile's browser data to Trash"
    )
    reset_parser.set_defaults(func=browser_reset_profile)
