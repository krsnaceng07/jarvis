"""JARVIS LLM Task infra extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import LLMTaskPlugin, llm_task_plugin, entry

__all__ = [
    "LLMTaskPlugin",
    "llm_task_plugin",
    "entry",
]
