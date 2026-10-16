"""CLI output mode detector for Google Meet subcommands."""

from __future__ import annotations

DEFAULT_JSON_COMMANDS = {"join", "status", "test-listen", "test-speech"}


def has_option(argv: list[str], flag: str) -> bool:
    for arg in argv[2:]:
        if arg == "--":
            return False
        if arg == flag or arg.startswith(f"{flag}="):
            return True
    return False


def is_google_meet_machine_output(argv: list[str]) -> bool:
    if len(argv) < 3:
        return False
    command = argv[2]
    return command in DEFAULT_JSON_COMMANDS or (
        command == "export" and has_option(argv, "--dry-run")
    )


def resolve_cli_output_mode(argv: list[str]) -> str:
    """Resolve CLI output format (json | text)."""
    if has_option(argv, "--json") or is_google_meet_machine_output(argv):
        return "json"
    return "text"


GOOGLE_MEET_CLI_DESCRIPTOR = {
    "name": "googlemeet",
    "description": "Join and manage Google Meet calls",
    "has_subcommands": True,
    "machine_output": is_google_meet_machine_output,
}
