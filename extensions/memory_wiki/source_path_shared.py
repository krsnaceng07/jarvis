"""source_path_shared — cross-platform artifact-key resolver.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/source-path-shared.ts``.

The memory-wiki plugin treats every artifact (raw
source file, memory page, daily note) by a stable
"artifact key" so downstream search and compile
pipelines can dedupe on the same string regardless of
which host the daemon runs on. The key is the
canonical realpath, lowercased on Windows (where the
filesystem is case-insensitive) and preserved as-is on
POSIX.
"""

from __future__ import annotations

import os
import sys

from jarvis_sdk import lowercase_preserving_whitespace


def resolve_artifact_key(absolute_path: str) -> str:
    """Return a stable artifact key for ``absolute_path``.

    Mirrors OpenClaw's ``resolveArtifactKey``. On
    POSIX the key is the canonical realpath; on
    Windows the realpath is lowercased (preserving
    internal whitespace) to match the case-insensitive
    filesystem. Symlink resolution failures fall back
    to the lexically-resolved path so the helper
    doesn't raise on a dangling symlink.
    """
    try:
        canonical = os.path.realpath(absolute_path)
    except (OSError, ValueError):
        canonical = os.path.abspath(absolute_path)
    if sys.platform == "win32":
        return lowercase_preserving_whitespace(canonical)
    return canonical


__all__ = ["resolve_artifact_key"]
