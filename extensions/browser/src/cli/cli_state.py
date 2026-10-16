"""CLI commands for browser state and settings."""

from typing import Any


def browser_cookies(args: Any) -> None:
    print("Cookies action")


def browser_storage(args: Any) -> None:
    print("Storage action")


def browser_set(args: Any) -> None:
    print("Set action")


def register_state_cli(subparsers: Any) -> None:
    # Cookies
    cookies = subparsers.add_parser("cookies", help="Manage cookies")
    cookies_subs = cookies.add_subparsers(dest="cookies_command")

    cookies_set = cookies_subs.add_parser("set")
    cookies_set.add_argument("name")
    cookies_set.add_argument("value")
    cookies_set.add_argument("--url")
    cookies_set.set_defaults(func=browser_cookies)

    cookies_clear = cookies_subs.add_parser("clear")
    cookies_clear.set_defaults(func=browser_cookies)
    cookies.set_defaults(func=browser_cookies)

    # Storage
    storage = subparsers.add_parser("storage", help="Manage storage")
    storage_subs = storage.add_subparsers(dest="storage_type")

    for stype in ["local", "session"]:
        stype_p = storage_subs.add_parser(stype)
        stype_subs = stype_p.add_subparsers(dest="storage_action")

        get_p = stype_subs.add_parser("get")
        get_p.set_defaults(func=browser_storage)

        set_p = stype_subs.add_parser("set")
        set_p.add_argument("key")
        set_p.add_argument("value")
        set_p.set_defaults(func=browser_storage)

        clear_p = stype_subs.add_parser("clear")
        clear_p.set_defaults(func=browser_storage)

    # Set
    set_p = subparsers.add_parser("set", help="Set options")
    set_subs = set_p.add_subparsers(dest="set_command")

    set_subs.add_parser("offline").add_argument("state")

    hdrs = set_subs.add_parser("headers")
    hdrs.add_argument("headers_json", nargs="?")
    hdrs.add_argument("--headers-json")

    creds = set_subs.add_parser("credentials")
    creds.add_argument("user", nargs="?")
    creds.add_argument("pass", nargs="?")
    creds.add_argument("--clear", action="store_true")

    geo = set_subs.add_parser("geo")
    geo.add_argument("lat", nargs="?")
    geo.add_argument("lon", nargs="?")
    geo.add_argument("--origin")
    geo.add_argument("--clear", action="store_true")

    set_subs.add_parser("media").add_argument("mode")
    set_subs.add_parser("timezone").add_argument("tz")
    set_subs.add_parser("locale").add_argument("loc")
    set_subs.add_parser("device").add_argument("dev")

    vp = set_subs.add_parser("viewport")
    vp.add_argument("width")
    vp.add_argument("height")

    for p in set_subs.choices.values():
        p.set_defaults(func=browser_set)
