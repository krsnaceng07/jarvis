"""jarvis.plugins.open_prose — OpenProse plugin & program execution engine.

OpenClaw parity: mirrors
``openclaw-main/docs/plugins/open-prose.md`` and
``openclaw-main/extensions/open-prose/index.ts``.

Commands:
- `/prose help`
- `/prose run <file.prose>`
- `/prose run <handle/slug>` (resolves to ``https://p.prose.md/<handle>/<slug>``)
- `/prose compile <file.prose>`
- `/prose examples`

State backends:
- `filesystem` (default): `.prose/runs/{id}/`
- `in-context`: transient context window
- `sqlite`: `.prose/runs/{id}/state.db`
- `postgres`: `OPENPROSE_POSTGRES_URL`

Features:
- `OpenProseConfig`: Plugin configuration model.
- `OpenProseRunState`: Run state holder.
- `resolve_prose_target_url()`: Resolves `handle/slug` shorthand to `https://p.prose.md/handle/slug`.
- `parse_prose_command()`: Parses slash command `/prose ...`.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

StateBackend = Literal["filesystem", "in-context", "sqlite", "postgres"]


@dataclass
class OpenProseConfig:
    enabled: bool = True
    state_backend: StateBackend = "filesystem"
    postgres_url: str | None = None


@dataclass
class OpenProseRunState:
    run_id: str
    program_path: str
    backend: StateBackend = "filesystem"
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


def resolve_prose_target_url(target: str) -> str:
    """Resolve `<handle>/<slug>` shorthand to canonical OpenProse URL."""
    trimmed = target.strip()
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        return trimmed
    if "/" in trimmed and not trimmed.endswith(".prose") and not Path(trimmed).exists():
        return f"https://p.prose.md/{trimmed}"
    return trimmed


@dataclass
class ParsedProseCommand:
    action: str
    target: str | None = None
    flags: dict[str, str] = field(default_factory=dict)


def parse_prose_command(raw_args: str) -> ParsedProseCommand:
    """Parse `/prose <action> [target]` slash command."""
    parts = raw_args.strip().split()
    if not parts:
        return ParsedProseCommand(action="help")

    action = parts[0].lower()
    target = parts[1] if len(parts) > 1 else None

    flags: dict[str, str] = {}
    for p in parts[2:]:
        if p.startswith("--state="):
            flags["state"] = p.split("=", 1)[1]

    return ParsedProseCommand(action=action, target=target, flags=flags)


__all__ = [
    "OpenProseConfig",
    "OpenProseRunState",
    "ParsedProseCommand",
    "StateBackend",
    "parse_prose_command",
    "resolve_prose_target_url",
]
