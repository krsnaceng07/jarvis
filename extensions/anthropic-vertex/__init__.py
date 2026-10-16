"""JARVIS Anthropic Vertex provider extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import AnthropicVertexProvider, anthropic_vertex_provider, entry

__all__ = [
    "AnthropicVertexProvider",
    "anthropic_vertex_provider",
    "entry",
]
