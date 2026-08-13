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

For full OpenClaw parity, use ``bootstrap_with_ritual()`` to run the
interactive three-beat identity ceremony after seeding.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jarvis_config_core import JarvisConfig
    from pathlib import Path

_log = logging.getLogger("src.bootstrap")

# The marker line we look for to know a file is still pristine.
_SEED_MARKER = "<!-- seeded by src.bootstrap; edit me -->"


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

<!-- seeded by src.bootstrap; edit me -->
"""

STARTER_IDENTITY_MD = """# Identity

JARVIS is a personal desktop AI assistant modeled after the JARVIS
character from Iron Man. The operator is referred to as "sir" by
default. JARVIS:

- Speaks concisely, with dry humor.
- Never claims to have done something it hasn't.
- Calls tools when needed; asks when blocked.
- Logs every action to the HUD log.

<!-- seeded by src.bootstrap; edit me -->
"""

STARTER_SOUL_MD = """# Soul

JARVIS's voice:

- "Yes, sir." / "Very good, sir." / "Right away, sir."
- Slight formality; never slang.
- Short sentences. No filler. No apologies.
- Humor is dry, never cruel.

If you change this file, the operator will hear the new voice in the
next session.

<!-- seeded by src.bootstrap; edit me -->
"""

STARTER_USER_MD = """# User

Operator's preferred name: Sir
Operator's timezone: (auto-detect at first run)
Operator's preferred language: en
Operator's notification style: voice (speak) + on-screen log

<!-- seeded by src.bootstrap; edit me -->
"""

STARTER_AGENTS_MD = """# Agent Instructions

Follow the workspace instructions in this file and any more specific
AGENTS.md file found below the current working directory.

<!-- seeded by src.bootstrap; edit me -->
"""

STARTER_BOOTSTRAP_MD = """# First-run setup

Complete the identity, user profile, and memory setup before normal
conversation. Delete this file when the ritual is complete.

<!-- seeded by src.bootstrap; edit me -->
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
    root_seeded: list[str] = field(default_factory=list)
    root_skipped: list[str] = field(default_factory=list)
    root_removed: list[str] = field(default_factory=list)


def seed_workspace(workspace: Path, skip_bootstrap: bool = False) -> BootstrapResult:
    """Seed the workspace's first-run files. Idempotent.

    ``workspace`` is the JARVIS workspace root. The seeder respects
    existing files: a user-edited IDENTITY.md is not touched.

    ``skip_bootstrap`` mirrors OpenClaw's ``--skip-bootstrap`` path: it
    keeps the workspace bootstrapped without creating the temporary
    ``BOOTSTRAP.md`` ritual marker.
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
    root_seeded: list[str] = []
    root_skipped: list[str] = []
    root_removed: list[str] = []

    workspace_configured = _is_workspace_configured(workspace)

    # OpenClaw's agent workspace is the canonical context root. Keep the
    # existing ``core/`` files for current JARVIS app consumers, but seed the
    # root contract so new agent sessions do not depend on that legacy layout.
    root_candidates = (
        workspace / "AGENTS.md",
        workspace / "SOUL.md",
        workspace / "IDENTITY.md",
        workspace / "USER.md",
        workspace / "MEMORY.md",
    )
    root_starters = (
        (workspace / "AGENTS.md", STARTER_AGENTS_MD),
        (workspace / "SOUL.md", STARTER_SOUL_MD),
        (workspace / "IDENTITY.md", STARTER_IDENTITY_MD),
        (workspace / "USER.md", STARTER_USER_MD),
        (workspace / "MEMORY.md", STARTER_MEMORY_MD),
    )
    brand_new_workspace = not any(path.exists() for path in root_candidates)
    for path, body in root_starters:
        if not path.exists():
            path.write_text(_seed_with_marker(body), encoding="utf-8")
            root_seeded.append(str(path))
        else:
            root_skipped.append(str(path))
    bootstrap_path = workspace / "BOOTSTRAP.md"
    if not skip_bootstrap and brand_new_workspace and not bootstrap_path.exists():
        bootstrap_path.write_text(_seed_with_marker(STARTER_BOOTSTRAP_MD), encoding="utf-8")
        root_seeded.append(str(bootstrap_path))
    elif bootstrap_path.exists() and workspace_configured:
        bootstrap_path.unlink()
        root_removed.append(str(bootstrap_path))

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
        root_seeded=root_seeded,
        root_skipped=root_skipped,
        root_removed=root_removed,
    )


def _is_workspace_configured(workspace: Path) -> bool:
    """True when the user has completed the first-run identity ritual."""
    for path in (
        workspace / "core" / "IDENTITY.md",
        workspace / "core" / "SOUL.md",
        workspace / "core" / "USER.md",
        workspace / "IDENTITY.md",
        workspace / "SOUL.md",
        workspace / "USER.md",
    ):
        if path.exists() and not _is_pristine(path):
            return True
    return False


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
    cfg: dict[str, object] = {
        "$schema": "./jarvis.schema.json",
        "_comment": (
            "JARVIS runtime config. Seeded by src.bootstrap on "
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


def bootstrap_with_ritual(
    workspace: Path,
    config: JarvisConfig,
    *,
    skip_bootstrap: bool = False,
) -> tuple[BootstrapResult, JarvisConfig]:
    """Full OpenClaw-parity bootstrap: seed workspace, run ritual, persist config.

    This implements the three-beat identity ceremony:
    1. Ask for agent name
    2. Ask for soul/vibe
    3. Ask for plugin preference

    Then persists choices to IDENTITY.md, SOUL.md, and config.json.

    Args:
        workspace: JARVIS workspace root
        config: Current JarvisConfig (will be updated with agent identity)
        skip_bootstrap: If True, skip the BOOTSTRAP.md marker but still run ritual

    Returns:
        Tuple of (BootstrapResult, updated JarvisConfig)
    """
    from .interactive import (
        run_bootstrap_ritual,
        persist_bootstrap_to_identity_files,
        persist_bootstrap_to_config,
    )

    # Step 1: Seed workspace files
    result = seed_workspace(workspace, skip_bootstrap=skip_bootstrap)

    # Step 2: Run interactive ritual (only on brand-new workspace)
    if not _is_workspace_configured(workspace):
        ritual_choices = run_bootstrap_ritual(workspace)

        # Step 3: Persist to identity files
        persist_bootstrap_to_identity_files(workspace, ritual_choices)

        # Step 4: Persist to config
        config = persist_bootstrap_to_config(config, ritual_choices)

        print("\n✓ Bootstrap ritual complete.")
        print(f"  Agent name: {ritual_choices['agent_name']}")
        print(f"  Soul: {ritual_choices['agent_soul'][:50]}...")
        print(f"  Plugin set: {'Minimal' if ritual_choices['minimal_plugins'] else 'Convenient'}")
        print()

    return result, config


__all__ = ["BootstrapResult", "seed_workspace", "bootstrap_with_ritual"]
