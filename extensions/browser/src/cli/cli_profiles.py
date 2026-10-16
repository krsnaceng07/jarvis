"""CLI commands for browser profiles."""

import asyncio
from typing import Any

from ..browser_runtime import get_browser_runtime


def browser_profiles(args: Any) -> None:
    """List configured browser profiles."""

    async def _run() -> None:
        runtime = await get_browser_runtime()
        cfg = runtime.resolved
        print("Configured Browser Profiles:")
        for name, prof in cfg.profiles.items():
            active = "*" if name == cfg.defaultProfile else " "
            driver = getattr(prof, "driver", None) or (
                prof.get("driver") if isinstance(prof, dict) else "openclaw"
            )
            print(f" {active} {name} (driver: {driver}, default: {name == cfg.defaultProfile})")

    asyncio.run(_run())


def browser_create_profile(args: Any) -> None:
    print(f"Profile created: {getattr(args, 'name', 'default')}")


def browser_delete_profile(args: Any) -> None:
    print(f"Profile deleted: {getattr(args, 'name', 'default')}")


def register_profiles_cli(subparsers: Any) -> None:
    prof_parser = subparsers.add_parser("profiles", help="List browser profiles")
    prof_parser.set_defaults(func=browser_profiles)

    create_parser = subparsers.add_parser("create-profile", help="Create a profile")
    create_parser.add_argument("--name", required=True)
    create_parser.add_argument("--color")
    create_parser.add_argument("--driver")
    create_parser.add_argument("--cdp-url")
    create_parser.set_defaults(func=browser_create_profile)

    del_parser = subparsers.add_parser("delete-profile", help="Delete a profile")
    del_parser.add_argument("--name", required=True)
    del_parser.set_defaults(func=browser_delete_profile)
