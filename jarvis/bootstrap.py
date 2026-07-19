"""Bootstrap — first-run seeder (mirror OpenClaw's ``docs/start/bootstrapping.md``).

On first launch against a brand-new workspace, JARVIS seeds:

  - ``config/jarvis.json`` (the runtime config; absent in Phase 0+1)
  - ``core/MEMORY.md`` (long-term memory; absent in Phase 0)
  - ``core/IDENTITY.md`` (the agent's identity — what it is, who it serves)
  - ``core/SOUL.md`` (the agent's voice / tone)
  - ``core/USER.md`` (the operator's name, preferences)

A workspace is considered "configured" once any of IDENTITY/SOUL/USER
has diverged from its starter template. We never overwrite user-edited
files (we check existence + a one-time marker in the file).

The OpenClaw bootstrap is an interactive ritual; JARVIS's is a
best-effort non-interactive seeder (the operator can edit the seeded
files post-hoc). This is intentional — JARVIS is a single-operator
desktop assistant, not a multi-channel agent platform.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_log = logging.getLogger("jarvis.bootstrap")

# The marker line we look for to know a file is still pristine.
_SEED_MARKER = "<!-- seeded by jarvis.bootstrap; edit me -->"


def _seed_with_marker(body: str) -> str:
    """Append the seed marker so we know not to re-seed."""
    return f"{body}\n\n{_SEED_MARKER}\n"


# ── Starter file contents ──────────────────────────────────────────

STARTER_MEMORY_MD = """# JARVIS Memory

Long-term notes JARVIS remembers across sessions. Format: keep one
fact per line, optionally tagged with `#category` (preference, fact,
person, project, todo). Example:

- The operator's name is Sir. #person
- Default browser is Chrome. #preference
- The 2026-07-20 launch is on track. #project

<!-- seeded by jarvis.bootstrap; edit me -->
"""

STARTER_IDENTITY_MD = """# Identity

JARVIS is a personal desktop AI assistant modeled after the JARVIS
character from Iron Man. The operator is referred to as "sir" by
default. JARVIS:

- Speaks concisely, with dry humor.
- Never claims to have done something it hasn't.
- Calls tools when needed; asks when blocked.
- Logs every action to the HUD log.

<!-- seeded by jarvis.bootstrap; edit me -->
"""

STARTER_SOUL_MD = """# Soul

JARVIS's voice:

- "Yes, sir." / "Very good, sir." / "Right away, sir."
- Slight formality; never slang.
- Short sentences. No filler. No apologies.
- Humor is dry, never cruel.

If you change this file, the operator will hear the new voice in the
next session.

<!-- seeded by jarvis.bootstrap; edit me -->
"""

STARTER_USER_MD = """# User

Operator's preferred name: Sir
Operator's timezone: (auto-detect at first run)
Operator's preferred language: en
Operator's notification style: voice (speak) + on-screen log

<!-- seeded by jarvis.bootstrap; edit me -->
"""


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """What the seeder actually wrote (so the host can log it)."""

    config_path: Path
    memory_path: Path
    identity_path: Path
    soul_path: Path
    user_path: Path
    seeded: list[str]  # list of paths the seeder created or refreshed
    skipped: list[str]  # list of paths the user already had


def seed_workspace(workspace: Path) -> BootstrapResult:
    """Seed the workspace's first-run files. Idempotent.

    ``workspace`` is the JARVIS workspace root. The seeder respects
    existing files: a user-edited IDENTITY.md is not touched.
    """
    config_dir = workspace / "config"
    core_dir = workspace / "core"
    config_dir.mkdir(parents=True, exist_ok=True)
    core_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / "jarvis.json"
    memory_path = core_dir / "MEMORY.md"
    identity_path = core_dir / "IDENTITY.md"
    soul_path = core_dir / "SOUL.md"
    user_path = core_dir / "USER.md"

    seeded: list[str] = []
    skipped: list[str] = []

    # config/jarvis.json — always (re)write; it's generated, not authored.
    if not config_path.exists():
        _seed_config(config_path)
        seeded.append(str(config_path))
    else:
        skipped.append(str(config_path))

    # Core files — only seed if missing or still pristine.
    for path, body, label in [
        (memory_path, STARTER_MEMORY_MD, "MEMORY.md"),
        (identity_path, STARTER_IDENTITY_MD, "IDENTITY.md"),
        (soul_path, STARTER_SOUL_MD, "SOUL.md"),
        (user_path, STARTER_USER_MD, "USER.md"),
    ]:
        if _is_pristine(path):
            path.write_text(_seed_with_marker(body), encoding="utf-8")
            seeded.append(str(path))
            _log.info("bootstrap: seeded %s", path)
        else:
            skipped.append(str(path))
            _log.info("bootstrap: kept user-edited %s", label)

    return BootstrapResult(
        config_path=config_path,
        memory_path=memory_path,
        identity_path=identity_path,
        soul_path=soul_path,
        user_path=user_path,
        seeded=seeded,
        skipped=skipped,
    )


def _is_pristine(path: Path) -> bool:
    """A file is pristine if it doesn't exist OR still has the seed marker."""
    if not path.exists():
        return True
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return True
    return _SEED_MARKER in text


def _seed_config(path: Path) -> None:
    """Write the default ``config/jarvis.json`` (idempotent — only called on first run)."""
    cfg = {
        "$schema": "./jarvis.schema.json",
        "_comment": (
            "JARVIS runtime config. Seeded by jarvis.bootstrap on "
            f"{datetime.now().isoformat(timespec='seconds')}. "
            "Edit values freely; the host reloads on next launch."
        ),
        "memory": {
            "backend": "sqlite",
            "path": "./core/memory.sqlite",
        },
        "voice": {
            "tts": "sapi",  # Windows SAPI default; macOS uses 'say', Linux uses 'espeak'.
            "rate_wpm": 195,
        },
        "hotkey": {
            "wake_word": "jarvis",
            "push_to_talk_key": "ctrl+space",
        },
        "channels": {
            "live": {"enabled": True},
        },
        "providers": {
            "default": "gemini",  # or "openrouter" once the openrouter plugin ships.
        },
    }
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = ["BootstrapResult", "seed_workspace"]
