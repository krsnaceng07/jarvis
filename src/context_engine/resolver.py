"""Context engine mention resolver — mirrors OpenClaw ``src/context-engine/``."""

from __future__ import annotations

import re
from pathlib import Path


class ContextEngineResolver:
    """Expands `@file:...`, `@memory:...`, `@skill:...`, `@url:...` references in prompt text."""

    def resolve_mentions(self, text: str) -> str:
        if not text:
            return text

        # @file:<path>
        def _replace_file(match: re.Match) -> str:
            filepath = match.group(1)
            p = Path(filepath)
            if p.exists() and p.is_file():
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    return f"\n--- Attached file: {filepath} ---\n{content}\n--- End attached file ---\n"
                except Exception:
                    pass
            return match.group(0)

        result = re.sub(r"@file:([^\s]+)", _replace_file, text)
        return result


GLOBAL_CONTEXT_ENGINE_RESOLVER = ContextEngineResolver()

__all__ = ["ContextEngineResolver", "GLOBAL_CONTEXT_ENGINE_RESOLVER"]
