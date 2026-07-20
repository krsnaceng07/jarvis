"""Public artifacts — exposes memory artifacts to other extensions + CLI.

Mirrors OpenClaw's
``extensions/memory-core/src/public-artifacts.ts``. The host
calls ``list_artifacts(params)`` to enumerate the memory
plugin's published artifacts (used by the doctor runner and
CLI).
"""
from __future__ import annotations

from typing import Any

from jarvis_sdk import MemoryPluginPublicArtifact


async def list_artifacts(
    params: dict[str, Any] | None = None,
) -> list[MemoryPluginPublicArtifact]:
    """List the public artifacts the memory_core plugin exposes.

    Returns:
      - ``memory.sqlite`` — the SQLite memory store (key/value
        long-term memory). Listed as ``kind="store"`` so the
        doctor runner can run an integrity check on it.
    """
    from pathlib import Path

    import os

    data_dir = Path(
        os.environ.get("JARVIS_DATA_DIR") or (Path.home() / ".jarvis")
    )
    db_path = data_dir / "core" / "memory.sqlite"
    return [
        MemoryPluginPublicArtifact(
            id="memory.sqlite",
            kind="store",
            path=str(db_path),
            description="SQLite-backed long-term memory (key/value).",
        )
    ]


__all__ = ["list_artifacts"]
