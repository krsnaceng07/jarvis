"""jarvis.shared.node_skill_constraints — node-skill payload limits.

OpenClaw parity: mirrors ``openclaw-main/src/shared/node-skill-constraints.ts``.
"""
from __future__ import annotations

import re

#: Maximum number of skills per node.
NODE_SKILL_MAX_COUNT = 64
#: Maximum bytes per individual skill content.
NODE_SKILL_MAX_CONTENT_BYTES = 64 * 1024
#: Maximum total bytes across all skills on one node.
NODE_SKILL_MAX_TOTAL_BYTES = 512 * 1024
#: Maximum description length (chars).
NODE_SKILL_MAX_DESCRIPTION_LENGTH = 1024
#: Canonical node-skill name pattern (lowercase, no ``--`` double-dash).
NODE_SKILL_NAME_RE = re.compile(r"^(?!.*--)[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


__all__ = [
    "NODE_SKILL_MAX_COUNT",
    "NODE_SKILL_MAX_CONTENT_BYTES",
    "NODE_SKILL_MAX_TOTAL_BYTES",
    "NODE_SKILL_MAX_DESCRIPTION_LENGTH",
    "NODE_SKILL_NAME_RE",
]
