"""jarvis.agents.sessions.frontmatter — YAML front-matter helpers.

OpenClaw parity: mirrors the
``stripFrontmatter`` helper in
``openclaw-main/src/agents/utils/frontmatter.ts``.

Phase 6.12c — STUB. The OpenClaw source
parses the ``---\\n...\\n---\\n`` block
at the head of a markdown file. The
Python port returns the text unchanged;
the full parser lands in Phase 6.13.
"""
from __future__ import annotations


def stripFrontmatter(content: str) -> str:
    """Strip a leading YAML front-matter
    block from ``content`` (if present)
    + return the rest.

    Mirrors ``stripFrontmatter``
    (``frontmatter.ts``).

    Phase 6.12c — STUB. Returns the
    text unchanged.
    """
    return content


__all__ = [
    "stripFrontmatter",
]
